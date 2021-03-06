import pandas as pd
import mne
import ParsingPandas
import json
import os
import sys
import gc
import re
import math
import time
#from parse import parse as parse
import xml.etree.ElementTree as ET

subidspellings = ["Subject", "subject", "SubjectID", "subjectid", "subjectID", "subid", "subID", "SUBID", "SubID",
                  "Subject ID", "subject id", "ID", "SF_SubID"]
starttimespellings = ["starttime", "startime", "start time", "Start Time","PSG Start Time", "Start"]

#characters that we will strip
STRIP = "' ', ',', '\'', '(', '[', '{', ')', '}', ']'"

#CODE FROM MNE TO READ KEMP FILES
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def read_edf_annotations(fname, annotation_format="edf/edf+"):
    """read_edf_annotations

    Parameters:
    -----------
    fname : str
        Path to file.

    Returns:
    --------
    annot : DataFrame
        The annotations
    """
    with open(fname, 'r', encoding='utf-8',
              errors='ignore') as annotions_file:
        tal_str = annotions_file.read()

    if "edf" in annotation_format:
        if annotation_format == "edf/edf+":
            exp = '(?P<onset>[+\-]\d+(?:\.\d*)?)' + \
                  '(?:\x15(?P<duration>\d+(?:\.\d*)?))?' + \
                  '(\x14(?P<description>[^\x00]*))?' + '(?:\x14\x00)'

        elif annotation_format == "edf++":
            exp = '(?P<onset>[+\-]\d+.\d+)' + \
                  '(?:(?:\x15(?P<duration>\d+.\d+)))' + \
                  '(?:\x14\x00|\x14(?P<description>.*?)\x14\x00)'

        annot = [m.groupdict() for m in re.finditer(exp, tal_str)]
        good_annot = pd.DataFrame(annot)
        good_annot = good_annot.query('description != ""').copy()
        good_annot.loc[:, 'duration'] = good_annot['duration'].astype(float)
        good_annot.loc[:, 'onset'] = good_annot['onset'].astype(float)
    else:
        raise ValueError('Not supported')

    return good_annot


def resample_30s(annot):
    annot = annot.set_index('onset')
    annot.index = pd.to_timedelta(annot.index, unit='s')
    annot = annot.resample('30s').ffill()
    annot = annot.reset_index()
    annot['duration'] = 30.
    return annot

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def EDF_file_Hyp(path):
    #using try and except right now because mne is broken on latest version and cannot read KEMP
    #***once updated get rid of except portion
    jsonObj = {}
    jsonObj["epochstage"] = []
    jsonObj["epochstarttime"] = []
    
    try:
        EDF_file = mne.io.read_raw_edf(path, stim_channel= 'auto', preload=True)
        TimeAndStage = mne.io.get_edf_events(EDF_file)           
        StartTime = 0
        for i in range(len(TimeAndStage) - 1):
            # calculate time for start of next stage
            EndTime = TimeAndStage[i + 1][0] - TimeAndStage[i][0]
            # use given duration of current stage
            Duration = TimeAndStage[i][1]

            j = 0
            while j < EndTime:
                # append NaN to json objct as epoch stage if duration of a stage
                # ends before the start of next stage
                # ***We do this because some of the data may not correlate to eachother
                if j <= Duration:
                    jsonObj["epochstage"].append(StartTime)
                else:
                    jsonObj["epochstage"].append("NaN")

                jsonObj["epochstarttime"].append(TimeAndStage[i][2])
                StartTime = StartTime + .5
                j = j + 30
        
        lastInterval = TimeAndStage[-1][0] + TimeAndStage[-1][1]
        StartTime = TimeAndStage[-1][0]
        while StartTime < lastInterval:
            jsonObj["epochstage"].append(StartTime)
            jsonObj["epochstarttime"].append(TimeAndStage[-1][2])
            StartTime = StartTime + .5

        # free memory
        del EDF_file
        del TimeAndStage
        gc.collect()
    
    
    except:
    
        annot = []
        #need to do try and except because edf++ uses different reading style
        try:
            annot = read_edf_annotations(path)
            annot = resample_30s(annot)

            mne_annot = mne.Annotations(annot.onset, annot.duration, annot.description)
            #Need to pull out important information here
            for i in range(len(mne_annot.description)):
                jsonObj["epochstage"].append(mne_annot.description[i])
                if i < 1:
                    jsonObj["epochstarttime"].append(float(mne_annot.duration[i])/60.0)
                else:
                    jsonObj["epochstarttime"].append(float(mne_annot.duration[i])/60.0 + jsonObj["epochstarttime"][-1])
    
        except:
            annot = read_edf_annotations(path,annotation_format="edf++")
            
            
            for lineIndex in range(len(annot.description)):
                if 'stage' in annot.description[lineIndex]:
                    stageRepeat = annot.duration[lineIndex]/60.0
                    numRepeat = 0
                    while numRepeat < stageRepeat:
                        jsonObj['epochstage'].append(annot.description[lineIndex])
                        if len(jsonObj['epochstarttime']) < 1:
                            jsonObj['epochstarttime'].append(0)
                        else:
                            jsonObj['epochstarttime'].append(.5 + jsonObj['epochstarttime'][-1])
                        numRepeat = numRepeat + .5               
    
        
        jsonObj['Type'] = '3'
    return jsonObj


def XMLRepeter (node):
    temp = {}
    list = []
    for child in node:
        J = (XMLRepeter(child))
        if len(J) != 0:
            for key in J.keys():
                if key in temp.keys():
                    temp[key].append(J[key])
                else:							#if J[key] != None:
                    temp[key] = []
                    temp[key].append(J[key])
        dict = {child.tag: child.text}
        if(child.text != '\n'):
            for key in dict.keys():
                if key in temp.keys():
                    temp[key].append(dict[key])
                else:							#if dict[key] != None:
                    temp[key] = []
                    temp[key].append(dict[key])
    return temp

def XMLParse(file):
    tree = ET.parse(file)
    root = tree.getroot()
    dictXML = XMLRepeter(root)
    tempDict= {}
    tempDict['epochstage'] = []
    tempDict['starttime'] = []
    tempDict['duration'] = []

    for key in dictXML.keys():
        needToStrip = str(dictXML[key]).split(',')
        for i in range(len(needToStrip)):
            needToStrip[i] = needToStrip[i].lstrip(STRIP).rstrip(STRIP)
        dictXML[key] = needToStrip

	# Need to change this maybe	right now only includes the important stuff
	# Need to fix the time
	#get dictionary with sleepevent, start time, and duration
	#need to expand so it will see every 30 sec and have it in epoch time
    for i in range(len(dictXML['EventType'])):
        if "Stages" in dictXML['EventType'][i]:
            tempDict['epochstage'].append(dictXML['EventConcept'][i])
            tempDict['duration'].append(float(dictXML['Duration'][i]))
            tempDict['starttime'].append(float(dictXML['Start'][i]))

    returnDict = {}
    returnDict['epochstage'] = []
    returnDict['epochstarttime'] = []
    returnDict['originalTime'] = StringTimetoEpoch(str(dictXML['ClockTime']).split(' ')[-1].lstrip(STRIP).rstrip(STRIP))
	#need to standardize
    for i in range(len(tempDict['epochstage'])):
        j = 0.0
        while j < (tempDict['duration'][i]):
            returnDict['epochstage'].append(tempDict['epochstage'][i].split('|')[0] )
            time = ( tempDict['starttime'][i] +  j )/ 60 + returnDict['originalTime']
            if time > 1440:
                time = time - 1440
            returnDict['epochstarttime'].append(time)
                
            j = j + 30
    returnDict['Type'] = 'XML'

    return returnDict

def getAllFilesInTree(dirPath):
    _files = []
    for folder, subfolders, files in os.walk(dirPath):
        for _file in files:
            filePath = os.path.join(os.path.abspath(folder), _file)
            _files.append(filePath)
    return _files


# parsing panda objects returns jason object
def Parsing(PandaFile):
    FileKeys = PandaFile.keys()
    # cycle through keys to see if we get hits on the five keys we want and keep track of which ones we hit

    output_dict = []
    for sub_data in PandaFile.iterrows():
        output_dict.append(sub_data[1].to_json())
    return output_dict


def StringTimetoEpoch(time):
    time = time.replace('.', ':')
    temp = time.split(":")
    #did this b/c of empty time lines 
    if temp[0] == '':
        return 0
    hours = int(temp[0])
    if temp[-1].find("AM") != -1 and temp[0].find("12"):
        hours = 0
    elif temp[-1].find("PM") != -1:
        hours = hours + 12
    # get rid of AM and PM
    temp[-1] = temp[-1].split(' ')[0]

    EpochTime = hours * 60 + int(temp[1]) + int(temp[2]) / 60
    EpochTime = round(EpochTime, 1)

    return EpochTime


def EpochtoStringTime(time):
    Sec = time % 60
    time = time / 60
    Min = time % 60
    time = time / 60
    TotalTime = str(time) + ':' + str(Min) + ":" + str(Sec)


# demographics file contains te data you would need fro the other one
# in the name of the demographics file it tells you which file to access for its data type
# from file path and name of scoring we know the SubjectID
# each file data base needs different parsing method
# we will neee a  checker to see which parse method is needed
# all demographics files contain same information


# returns an integer determiing which parse method to use
# if found == 0 file contain only s and 0s
# if found == 1 file contain latency and type(sleep stage mode)
# if found == 2 file contain sleep stage , and time
KeyWords = ["latency", "RemLogic"]


def ScoringParseChoose(file):
    found = 0
    firstline = file.readline()
    file.seek(0)
    for count in range(len(KeyWords)):
        if firstline.find(KeyWords[count]) != -1:
            found = count + 1
    return found


# Type 0
def BasicScoreFile(file):
    JasonObj = {}
    JasonObj["epochstage"] = []
    JasonObj["Type"] = "0"
    for line in file:
        temp = line.split(' ')
        temp = temp[0].split('\t')
        temp[0] = temp[0].strip('\n')
        JasonObj["epochstage"].append(temp[0])
    return JasonObj


# Type 1		Example: SpencerLab
# these files give time in seconds in 30 sec interval
# start of sleep time is given in demographic file
def LatTypeScoreFile(file):
    JasonObj = {}
    JasonObj["Type"] = "1"
    JasonObj["epochstage"] = []
    JasonObj["epochstarttime"] = []
    file.readline()  # done so that we can ignore the first line which just contain variable names
    for line in file:
        temp = line.rstrip()
        temp = line.split('  ')
        if len(temp) == 1:
            temp = line.split('\t')
        temp[-1] = temp[-1].strip('\n')
        JasonObj["epochstage"].append(temp[-1])
        time = temp[0]
        time = int(time) / 60
        JasonObj["epochstarttime"].append(time)
    return JasonObj


# Type 2
def FullScoreFile(file):
    JasonObj = {}
    JasonObj["Type"] = "2"
    JasonObj["epochstage"] = []
    JasonObj["epochstarttime"] = []
    # find line with SleepStage
    # find position of SleepStage and Time
    StartSplit = False

    SleepStagePos = 0
    TimePos = 0
    EventPos = 0

    for line in file:
        if StartSplit and line.strip() != '':
            temp = line.split('\t')

            if len(temp) > EventPos and temp[EventPos].find("MCAP") == -1:
                JasonObj["epochstage"].append(temp[SleepStagePos])
                time = StringTimetoEpoch(temp[TimePos])
                JasonObj["epochstarttime"].append(time)

        if line.find("Sleep Stage") != -1:
            StartSplit = True
            temp = line.split('\t')
            for i in range(len(temp)):
                if temp[i] == "Sleep Stage":
                    SleepStagePos = i
                if temp[i].find("Time") != -1:
                    TimePos = i
                if temp[i].find("Event") != -1:
                    EventPos = i
    return JasonObj

def GetSubIDandStudyID(filePath, CurrentDict):
    
    studyid = 'n/a'
    subjectid = 'n/a'
    visitid = 1
    
    if 'scorefiles' in filePath:
        studyid = filePath.split('scorefiles')[0]
        studyid = studyid.split('\\')
        if studyid[-1] == '':
            studyid = studyid[-2]
        else:
            studyid = studyid[-1]
        subjectid =  filePath.split('scorefiles')[-1]
        subjectid = subjectid.split('subjectid')[-1]       
        subjectid = subjectid.split('.')[0]
        if 'visit' in filePath:
            visitid = subjectid.split('visit')[-1]
            visitid = visitid,split('.')[0]
            subjectid = subjecid.split('visit')[0]
    
    subjectid = str(subjectid).lstrip(STRIP).rstrip(STRIP)
    visitid = str(visitid).lstrip(STRIP).rstrip(STRIP)
    studyid = str(studyid).lstrip(STRIP).rstrip(STRIP)
    CurrentDict['subjectid'] = subjectid
    CurrentDict['studyid'] = studyid
    CurrentDict['visitid'] = visitid
    return CurrentDict



# gets the file reads it using appropriate read method then calls appropriate parse function
# does fine tuning for jason obj to uniform include subjectID and studyid
def MakeJsonObj(file):
    # demographic Files
    if file.endswith("xls") or file.endswith("xlsx") or file.endswith(".csv"):
        # add studyid from name of file
        temp = file.split('.')
        temp = temp[0].split('\\')
        temp = temp[-1].split('ics_')
        temp = temp[-1]

        #Gives us the number of sheets in the excel file
        xl = pd.ExcelFile(file)
        numSheets = 0
        for sheets in range(len(xl.sheet_names)):
            numSheets += 1
        
        if(numSheets < 8):
            # do the parsing
            JsonList = ParsingPandas.main(file)
            for i in range(len(JsonList)):
                JsonList[i] = json.loads(JsonList[i])
            
            returningList = []
            for i in range(len(JsonList)):
                if "subjectid" not in JsonList[i]:
                    # checks for all the common different spellings of subjectid and casts it to subjectid in dict
                    for spell in subidspellings:
                        if spell in JsonList[i]:
                            JsonList[i]["subjectid"] = JsonList[i][spell]
                    # subjectid becomes N/A if comon spelling for subjectid not found
                    if "subjectid" not in JsonList[i]:
                        JsonList[i]["subjectid"] = 'N/A'

                    # if subject id is a word makes it into all lowercase
                    if isinstance(JsonList[i]["subjectid"], str):
                        JsonList[i]["subjectid"] = JsonList[i]["subjectid"].lower()

                JsonList[i]["studyid"] = temp
            # JsonList[i]["visitid"] = visit

            return JsonList
            
        elif(numSheets>=8):
            JsonDict = {}
            JsonDict["subjectid"] = temp
            JsonDict["epochstarttime"] = []
            JsonDict['epochstage'] = []
            
            temp1 = pd.read_excel(file, sheetname="list")
            temp2 = pd.read_excel(file, sheetname="GraphData")
        
            epoch = 0
            time = ""
            for i in temp1.iterrows():
                if(i[1][1] == "RecordingStartTime"):
                    time = i[1][2]
                    break
            
            #TEST
            JsonDict = GetSubIDandStudyID(file, JsonDict)
            if(JsonDict['subjectid'] == "496"):
                time = "13:44:52"
            if(JsonDict['subjectid'] == "352"):
                time = "13:44:52"
            if(JsonDict['subjectid'] == "369"):
                time = "13:44:52"
            #TEST
            epoch = StringTimetoEpoch(time)
            if epoch == 0:
                    print(file)
                    
            epoch = epoch - 0.5

            for i in temp2.iterrows():
                if not(math.isnan(i[1][1])):
                    JsonDict['epochstage'].append(int(i[1][1]))
                    epoch += 0.5
                    if(epoch >= 1440):
                        epoch = epoch - 1440
                    JsonDict['epochstarttime'].append(epoch)
                else:
                    JsonDict['epochstage'].append(-1)
                    epoch += 0.5
                    if(epoch >= 1440):
                        epoch = epoch - 1440
                    JsonDict['epochstarttime'].append(epoch)
            JsonDict = GetSubIDandStudyID(file, JsonDict)  
            JsonDict["Type"] = "Cellini"
                        
            return JsonDict
    # these are the scoring files (txt)
    elif file.endswith(".txt"):
        JSON = {}
        temp = open(file, 'r')
        ScoreFileType = ScoringParseChoose(temp)
        if ScoreFileType == 0:
            JSON = BasicScoreFile(temp)
        elif ScoreFileType == 1:
            JSON = LatTypeScoreFile(temp)
        elif ScoreFileType == 2:
            JSON = FullScoreFile(temp)
        else:
            print("other")

        # add studyid and subectID to JSON for scoring
        JSON = GetSubIDandStudyID(file, JSON)
        return JSON

    # EDF+ files which contain scoring data
    elif file.endswith(".edf"):
        JSON = {}
        JSON = EDF_file_Hyp(file)
        
        # add studyid and subectID to JSON for scoring
        JSON = GetSubIDandStudyID(file, JSON)
        return JSON

    elif file.endswith('.xml'):
        JSON = {}
        JSON = XMLParse(file)

    return 1


# Demo is a list of dictionary from demographic files
# Score is  list of dictionary from all score files
def CombineJson(Demo, Score):
    ReturnJsonList = []
    # this for loop goes through all the demographics data
    for i in range(len(Demo)):  # FIXME, what is i, what is it indexing over? be more specific
        Found = False
        # this for loop goes through all the scoring datas
        for j in range(len(Score)):  # FIXME, what is j, what is it indexing over? be more specific
            # check if the studyid and subjectid of the data is the same
            if str(Demo[i]["studyid"]) == str(Score[j]["studyid"]) and str(Demo[i]["subjectid"]) == str(Score[j]["subjectid"]):
                temp = {**Demo[i], **Score[j]}  # FIXME temp what? be more specific
                # type 0 files have epoch timestamps we add it now
                if temp[
                    "Type"] == '0':  # FIXME if type is an int in char form, can you make it meaninginful, otherwise it should be type int
                    temp["epochstarttime"] = []
                    for spell in starttimespellings:
                        if spell in temp.keys():
                            temp["epochstarttime"].append(StringTimetoEpoch(temp[spell]))

                    for samples in range(len(temp["epochstage"]) - 1):
                        epochTime = temp["epochstarttime"][samples] + .5
                        if epochTime >= 1440:
                            epochTime = 0
                        temp["epochstarttime"].append(epochTime)

                # type 1 files need to add the time sleeping to start time from demographics file data
                elif temp["Type"] == '1' or temp["Type"] == '3':
                    StartTime = 0

                    for spell in starttimespellings:
                        if spell in temp.keys():
                            StartTime = StringTimetoEpoch(temp[spell])

                    for index in range(len(temp["epochstarttime"])):
                        CheckOver = temp["epochstarttime"][index] + StartTime
                        if CheckOver >= 1440:
                            CheckOver = CheckOver - 1440
                        temp["epochstarttime"][index] = CheckOver

                ReturnJsonList.append(temp)
                Found = True

        if Found == False:
            print("no match found for: " + str(Demo[i]["studyid"]) + ", " + str(Demo[i]["subjectid"]))

    return ReturnJsonList


# Parameter JsonList created from one demographics file of a particular study
#          JsonList created from all score files for the same study
#		   file  is the absolute path where new directory jsonObjects will be created which contain the data from score+demographic
def CreateJsonFile(JsonObjListDemo, JsonObjList, file):
    # call function to combine the lists into one json obj
    FinishedJson = CombineJson(JsonObjListDemo, JsonObjList)
   
    # save each object(patient) as own file
    # create a folder in original file path
    # save all objects in folder as file
    directory = file + "/jsonObjects"
    if not os.path.exists(directory):
        os.mkdir(directory)
    for Object in FinishedJson:
        if len(Object['epochstage']) != len(Object['epochstarttime']):
            print(Object['subjectid'])
            exit()
            
        # study_subid_visit_session     <-- session not added yet
        if "session" in Object.keys():
            filename = directory + '/' + str(Object["studyid"]) + "_subjectid" + str(
                Object["subjectid"]) + "_visit" + str(Object["visitid"]) + "_session" + str(Object["session"]) + ".json"
        else:
            filename = directory + '/' + str(Object["studyid"]) + "_subjectid" + str(
                Object["subjectid"]) + "_visit" + str(Object["visitid"]) + ".json"
        jsonfile = open(filename, 'w')
        json.dump(Object, jsonfile)   
        
        
    return

def studyFolders(dirPath):
    _files = []
    studyFolders = []
    #In case we are looking at a file that isn't in /scorefiles/
    studyFolderHead = -1
    for folder, subfolders, files in os.walk(dirPath):
        for _file in files:
            filePath = os.path.join(os.path.abspath(folder), _file)
            if(filePath.find('/') != -1):
                holder = filePath.split('/')
            else:
                holder = filePath.split('\\')
            #Get study folder lab name position
            for i in range(len(holder)):
                if((holder[i].find("scorefiles") != -1) or (holder[i].find("edf") != -1)):
                    studyFolderHead = i
                    break
            if(studyFolderHead == -1):
                break
            location = ""
            #Get the study folder lab name
            for i in range(studyFolderHead):
                if(i != 0):
                    location = location + '\\' + holder[i]
            #Append to list of study Folders
            if(location not in studyFolders):
                studyFolders.append(location)
                break

            studyFolderHead = -1

    return studyFolders

#Works with CAPStudy(kinda) and DinklemannLab
def sleepStageMap(fileToMap,stageMap):    
    #first for loop go loop around all dictionaries
    for i in range(len(fileToMap)):
        CurStageVar = fileToMap[i]['epochstage']
        TempEpochStage = []
        #loop around all items in epoch stage in this dictionary
        for j in range(len(CurStageVar)):
            UnableToFindMapping = True
            #loop around all items in stagemap to see if there is a match
            for k in range(len(stageMap)):
                if str(stageMap[k]['mapsfrom']) == str(CurStageVar[j]):
                    TempEpochStage.append(stageMap[k]['mapsto'])
                    UnableToFindMapping = False
                    break
            if UnableToFindMapping:
                TempEpochStage.append(-1)
        fileToMap[i]['epochstage'] = TempEpochStage

    return fileToMap


# Main
# main chooses which parsing function is called
# Three methods of using the function
# 1) input the file path into main when called
# 2) input the file path as the first index of the cmd line argument
# 3) call main with no parameters and cmd line argument and manulally input when prompted
if __name__ == '__main__':  # bdyetton: I had to edit this file a little, there are some comments on tips and improvements (just for the bits i have looked at)
    if len(sys.argv) > 1:
        file = sys.argv[1]  # FIXME using file and files as variable names is confusing, be more specific
    else:
        file = input("Enter absolute path to the head Directory containing the scorings folders: ")

    # now we have (need?) a list of Json Objs made from all files in folder
    # fist will contain all json obj from the score files
    # second will contain all json objs from demographic files
    JsonObjList = []
    JsonObjListDemo = []
    EpochStageMap = []

    FolderList = studyFolders(file)

    for files in FolderList:# FIXME files is a single element, and therefore it should be file (non pural)
        Study = getAllFilesInTree(files)
        CheckEDFfolder = True

        #make sure that we do not access edfs directory in study if there is a scorefiles directory
        #by setting Check EDFfolder to false
        for Checking in Study:
            if 'scorefile' in Checking:
                CheckEDFfolder = False
                break
        for studyfile in Study:

	        #temp = GetSubIDandStudyID(files, temp)  # FIXME Do not use temp as a varible, there is always a more decriptive name
            # Need to set studyid of current study
            # if study id changes it means we are in different study folder
            # so we can connect the Json objects and create the json files
            # FIXME i dont think this is a very safe move, there may be .xlsx files that do not represent a new study

            if ('scorefiles' in studyfile ) or ('edfs' in studyfile and CheckEDFfolder) or ('Demographics' in studyfile) or ('stagemap' in studyfile):
                JsonObj = MakeJsonObj(studyfile)
                if isinstance(JsonObj, int):
                    print(studyfile + " is not comprehendable")
                elif 'scorefile' in studyfile:
                    JsonObjList.append(JsonObj)
                elif 'Demographics' in studyfile:
                    for i in JsonObj:
                        JsonObjListDemo.append(i)
                elif 'stagemap' in studyfile:
                    for i in JsonObj:
                        EpochStageMap.append(i)
        
        JsonObjList = sleepStageMap(JsonObjList, EpochStageMap)
        gc.collect()
        #print(type(JsonObjList[0]['subjectid']))
        #print(type(JsonObjListDemo[-1]['subjectid']))
        #if JsonObjList[0]['subjectid'] == str(JsonObjListDemo[-1]['subjectid']):
        #    print('subjectid is same')
        #else:
        #    if int( JsonObjList[0]['subjectid']) == int(JsonObjListDemo[-1]['subjectid']):
        #        print('int cast')
        #    else:
        #        print(JsonObjList[0]['subjectid'])
        #        print(JsonObjListDemo[-1]['subjectid'])
        #if JsonObjList[0]['studyid'] == JsonObjListDemo[-1]['studyid']:
        #    print('studyid is same')
        #else:
        #    print('BROKEN')
        #    print(JsonObjList[0]['studyid'])
        #    print(JsonObjListDemo[-1]['studyid'])
        #print(JsonObjList[0])
        #print(JsonObjListDemo[-1])
        #exit()
        CreateJsonFile(JsonObjListDemo, JsonObjList, file)  # FIXME a more appropreate name would be save json file
        JsonObjListDemo = []
        JsonObjList = []
        EpochStageMap = []
        gc.collect()

    #CreateJsonFile(JsonObjListDemo, JsonObjList, file)
