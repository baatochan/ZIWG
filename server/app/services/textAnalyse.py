from flask import json
import requests
import xml.etree.ElementTree as ET
from app.services.db import db
from app.models.graph import Graph

clarinpl_url = "http://ws.clarin-pl.eu/nlprest2/base"
url = clarinpl_url + "/process"
user_mail = "testo@.test.pl"
# Tag and recognize named entities (coarse-grained categories)
lpmn = 'wcrft2|liner2({"model":"top9"})'

text = "Paweł robi zadanie z Przemek.\
Przemek współpracuje z Pawłem.\
Wojtek pisze jutro Kolokwium z angielskiego.\
Przemek pisze kolokwium z Wojtkiem.\
Bartosz zrobił już coś.\
Np. Bartosz zna się tylko z Pawłem.\
Reszta grupy jest nieznana.\
Mariusz jedzie autem Mariuszem."


def main(text, id):
    # Get analyzed XML
    info = getTextInf(text)
    windowSize = 80

    dependendencyTable = []
    index = 0
    weight = 2**index

    # Entity matrix
    table = tableInit(info[0], info[1], info[2], info[3], info[4], weight)
    dependendencyTable = table[0]
    personsTable = table[1]

    # -1 because of empty string at the end of text
    sentencesAmount = len(text.split('.')) - 1
    windowSize = 200

    # Get entities relation
    div2(info, dependendencyTable, personsTable, sentencesAmount, windowSize)
    # floating_window(info, dependendencyTable, personsTable, sentencesAmount)

    i = 0
    for r in dependendencyTable:
        i += 1

    r = parseData(dependendencyTable, personsTable)
    f = open("demofile2.txt", "a")
    f.write(json.dumps(r))
    f.close()

    g = Graph.query.filter_by(id=id).first()
    g.nodesData = json.dumps(r)
    g.ready = 1
    db.session.commit()

    return r


def ccl_orths(ccl):
    tree = ET.fromstring(ccl)
    return [orth.text for orth in tree.iter('orth')]


def ccl_bases(ccl):
    tree = ET.fromstring(ccl)
    return [tok.find('./lex/base').text for tok in tree.iter('tok')]


def ccl_poses(ccl):
    tree = ET.fromstring(ccl)
    return [tok.find('./lex/ctag').
            text.split(":")[0] for tok in tree.iter('tok')]


def ccl_ctag(ccl):
    tree = ET.fromstring(ccl)
    return [tok.find('./lex/ctag').
            text.split(":") for tok in tree.iter('tok')]


def ccl_ann(ccl):
    tree = ET.fromstring(ccl)
    annot = []
    for tok in tree.iter('tok'):
        buff = tok.find("ann")
        if (buff is None):
            annot.append(0)
        else:
            annot.append(int(buff.text))
    return annot


def getTextInf(textToSend):
    payload = {'text': textToSend, 'lpmn': lpmn, 'user': user_mail}
    headers = {'content-type': 'application/json'}
    r = requests.post(url, data=json.dumps(payload), headers=headers)

    ccl = r.content.decode('utf-8')
    bases = ccl_bases(ccl)
    poses = ccl_poses(ccl)
    ctag_attr = ccl_ctag(ccl)
    annot = ccl_ann(ccl)

    return [ccl, bases, poses, ctag_attr, annot]


def check_entity(annot, ctag, base, arr, cnt):
    if ((annot > 0) and ("subst" in ctag and "m1" in ctag)):
        if str(base) in arr:
            pI = arr.index(base)
            cnt[pI] = cnt[pI] + 1
        else:
            arr.append(base)
            cnt.append(1)


def tableInit(xml, bases, poses, ctag_attr, annot, weight):
    len_words = len(poses)
    count = []
    personsTable = []

    for i in range(0, len_words-1):
        check_entity(annot[i], ctag_attr[i], bases[i], personsTable, count)

    len_ent = len(personsTable)

    global table_result
    table_result = [[0 for i in range(len_ent)] for j in range(len_ent)]

    for i in range(0, len_ent):        # entity matrix
        for j in range(0, len_ent):
            if i == j:
                table_result[i][j] = 0
            else:
                table_result[i][j] += (count[i] * weight)
                table_result[j][i] += (count[i] * weight)
    return [table_result, personsTable]


def div2(info, dependendencyTable, personsTable,
         sentencesAmount, initWindowSize):
    # Utilising global result and info arrays
    for z in range(0, sentencesAmount):
        windowSize = int(initWindowSize / (2 ** z))
        if (windowSize >= 1):
            weight = 2**z
            for i in range(0, sentencesAmount - 1, windowSize):
                personsFromWindow = findPersonInWindow(info, i, i + windowSize,
                                                       sentencesAmount)
                increaseConnections(dependendencyTable, personsTable,
                                    personsFromWindow, weight)
        else:
            break


def floating_window(info, dependendencyTable, personsTable, sentencesAmount):
    windowSize = sentencesAmount
    windowStep = 1
    weight = 1
    weightStep = 2
    windowFloatStep = 1
    # We are decreasing the window size
    # and increasing the relation weight in each step
    while (windowSize >= 1):
        # Last possible position of window (due to its size)
        lastWinPos = sentencesAmount - windowSize
        for windowStart in range(0, lastWinPos + 1, windowFloatStep):
            windowEnd = windowStart + windowSize - 1
            if (windowEnd >= sentencesAmount):
                windowEnd = sentencesAmount - 1
            personsFromWindow = findPersonInWindow(info, windowStart,
                                                   windowEnd, sentencesAmount)
            increaseConnections(dependendencyTable, personsTable,
                                personsFromWindow, weight)
        windowSize -= windowStep
        weight *= weightStep


def findPersonInWindow(info, indexStart, indexStop, max):
    stop = indexStop
    start = indexStart

    if indexStop > max:
        stop = max

    # Empty array for entities cnt
    bases = info[1]
    poses = info[2]
    ctag_attr = info[3]
    annot = info[4]
    len_words = len(poses)
    entities = []
    count = []
    isInWindow = False
    dotCount = 1

    for i in range(0, len_words-1):
        if poses[i] == 'interp' and poses[i-1] != 'brev':
            dotCount += 1

        if start <= dotCount:
            isInWindow = True
        if stop < dotCount:
            isInWindow = False
            break

        if isInWindow:
            check_entity(annot[i], ctag_attr[i], bases[i], entities, count)

    return [entities, count]


def increaseConnections(dependendencyTable, personsTable,
                        winPersonsCnt, weight):
    entities = winPersonsCnt[0]
    count = winPersonsCnt[1]
    len_ent = len(entities)

    for i in range(0, len_ent):
        person = personsTable.index(entities[i])
        for r in range(0, len_ent):
            if r != i:
                personRel = personsTable.index(entities[r])
                relStr = (count[i] * weight)
                dependendencyTable[person][personRel] += relStr
                dependendencyTable[personRel][person] += relStr
                dependendencyTable[person][person] += count[i]


def check_conn_threshold(conn, threshold):
    if (conn <= threshold):
        return True
    else:
        return False


def calc_conn_threshold(dependendencyTable, perc=5, edge_thresh=1500):
    edge_max = len(dependendencyTable) ** 2
    edges = []
    for i in range(0, len(dependendencyTable)):
        for j in range(0, len(dependendencyTable)):
            edges.append(dependendencyTable[i][j])
    edges.sort()
    if (edge_max > edge_thresh):
        return edges[edge_max - 1 - edge_thresh]
    else:
        rm_edge = int((edge_max - 1) * perc / 100)
        return edges[rm_edge]


def parseData(dependendencyTable, personsTable):
    x = ''
    x += '{'
    x += '"nodes": ['
    pLen = len(personsTable)

    maxP = maxPersonCnt(dependendencyTable, personsTable)
    for p in range(0, pLen):
        if p != 0:
            x += ', '
        x += '{ "name": "' + personsTable[p] + '", '
        x += '"class": "'
        x += personClassification(dependendencyTable,
                                  personsTable,
                                  dependendencyTable[p][p])
        x += '", '
        x += '"occurrence": ' + str(int(dependendencyTable[p][p]/maxP*100))
        x += ' }'
    x += '],'
    x += ' "links": ['

    lenP = len(personsTable)
    data = ''
    z = 0

    max = maxValOfConnection(dependendencyTable, personsTable)
    thresh = calc_conn_threshold(dependendencyTable)

    for i in range(0, lenP):
        for j in range(1+z, lenP):
            if (not check_conn_threshold(dependendencyTable[i][j], thresh)):
                data += '{ "source": ' + str(i) + ', "target": ' + str(j) + \
                    ', "value": ' + \
                    str(int(dependendencyTable[i][j] / max * 100)) + \
                    ', "type": "' + \
                    connectionClassification(dependendencyTable, personsTable,
                                             dependendencyTable[i][j]) + '" }'
                data += ', '
        z += 1

    data = data[:-2]
    x += data
    x += '] }'

    y = json.loads(x)

    return y


def personClassification(dependendencyTable, personsTable, cnt):
    max = maxPersonCnt(dependendencyTable, personsTable)

    if cnt > (max * 2/3):
        return 'frequent'
    elif cnt > (max * 1/3):
        return 'normal'
    else:
        return 'rare'


def connectionClassification(dependendencyTable, personsTable, weight):
    max = maxValOfConnection(dependendencyTable, personsTable)

    if weight > (max * 1/2):
        return 'straight'
    else:
        return 'dotted'


def maxValOfConnection(dependendencyTable, personsTable):
    max = 1

    lenP = len(personsTable)
    z = 0

    for i in range(0, lenP):
        for j in range(1+z, lenP):
            if dependendencyTable[i][j] > max:
                max = dependendencyTable[i][j]
        z += 1

    return max


def maxPersonCnt(dependendencyTable, personsTable):
    max = 1

    lenP = len(personsTable)

    for i in range(0, lenP):
        if dependendencyTable[i][i] > max:
            max = dependendencyTable[i][i]

    return max


if __name__ == "__main__":
    main(text)
