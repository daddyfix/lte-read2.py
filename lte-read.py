#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" ----------------------------------------------------------
CHANGELOG
Oct 2 2020
    - Fixed --shortcodes bug
    - Fixed --showlist bug

Jan 1 2020
    - Added function to allow output of more than one search key
      by allowing multiple keys (-k)
      ie. -k from -k datetime
      keys is now a list of lists

----------------------------------------------------------- """ 

""" ----------------------------------------------------------

    Install Modules if not installed

---------------------------------------------------------- """
import pip, time, sys
for im in ["serial", "humanfriendly", "magic", "python-dateutil", "Pillow"]:
    try:
        pkg = im
        if 'dateutil' in im:
            pkg='dateutil'
        elif 'Pillow' in im:
            pkg='PIL'
        globals()[pkg] = __import__(pkg)
    except ImportError:
        if 'Pillow' in im:
            print ("Cannot install Pillow via pip install")
            print ("Please install via ...")
            print ("sudo apt-get install python-imaging")
            sys.exit()
        print ("Installing "+im+" module...")
        pip.main(['install', im])
        time.sleep(2)


""" ------------------------------------------------------------

    Import Modules

-------------------------------------------------------------"""
# PySerial
import serial
import serial.tools

# System
import datetime
from datetime import timedelta
import dateutil
from dateutil import parser
from dateutil import tz
import inspect
import os
import logging
import glob
import json
import time

# sorting sort()
from operator import itemgetter

# Removine Duplicates in list
import itertools

#import operator
#from operator import itemgetter, attrgetter

# Convertions
import humanfriendly
import magic
import PIL
from PIL import Image

#sys.exit()
# Load Python file as args
import ast

# Regex
import re

# Parse the Arguments passed to this script
import argparse

# URL/Web Functions
import urllib
import urllib.request
import urllib3
import urlparse2

# Database
import sqlite3
from sqlite3 import Error

# Run Linux Scripts
import subprocess

#Global Variables
ser = 0
debug = False
#debug = True

errorcodes =  False
textfile_holder=''
imagefile_holder=''
gConn=None
SMSAction = []

# At Commands
AT_COMMAND={
    'read':'CMGR',
    'delete':'CMGD'
}

# Paths and Log Filenames
filename = inspect.getframeinfo(inspect.currentframe()).filename
modem_files_path = os.path.dirname(os.path.abspath(filename))+'/modem_tmp_files/'
modem_file_cutoff_in_days = 10
imagepath = '/nfs/mycloud/mobilesvr/movie_posters/'
filebase = os.path.splitext(filename)[0]
logfile = '/nfs/mycloud/mobilesvr/logs/lte-read.py.log'
errorCodesFile = os.path.dirname(os.path.abspath(filename))+'/errorcodes.py'
atfile = os.path.dirname(os.path.abspath(filename))+'/at_commands.txt'
lastReadIdsFile = os.path.dirname(os.path.abspath(filename))+'/lte-read-history.txt'

# Connection Details
default_baudrate='115200'
default_port='/dev/ttyUSB3'

logging.basicConfig(filename=logfile,level=logging.DEBUG)
#logging.debug('This message should go to the log file')
#logging.info('So should this')
#logging.warning('And this, too')

# Trim files
rc = subprocess.call("echo \"$(tail -n 150 "+logfile+")\" > "+logfile, shell=True)
rc = subprocess.call("echo \"$(tail -n 150 "+atfile+")\" > "+atfile, shell=True)


char_ascii={}
char_ascii[0]= { 'desc' : 'Character Set',
                    'query': 'AT+QMMSCFG="character"', 
                    'expected': 'ASCII', 
                    'correct': 'AT+QMMSCFG="character","ASCII"'}
      

def get_date():
    return (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))





""" =====================================================

    Serial Communications

========================================================="""



""" --------------------------------------
    Initialize the Serial Port
-------------------------------------- """
def init_serial():

    global ser          # Must be declared in Each Function

    ser = serial.Serial()

    ser.baudrate = args['baudrate']

    # enable hardware control
    ser.rtscts = False
    
    ser.port = args['port']

    #Specify the TimeOut in seconds, so that SerialPort
    #Doesn't hangs
    ser.timeout = 0

    # -----------------------------------
    # Check is the Serial Port is being used 
    # -----------------------------------
    cmd = "sudo lsof | grep "+ser.port

    while True:
        p = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE)
        output = p.communicate()[0]
        if output:
            msg = 'Serial Port ' + str(ser.port) + ' ' + str(ser.baudrate) + ' is being used by ...'
            debug_msg(msg)
            txt = output.split('\n')
            for line in txt:
                if line:
                    val = line.split()
                    msg = str(val[0]) + ' PID: ' + str(val[1])
                    debug_msg(msg)

            debug_msg("Trying again in 60 seconds...")
            time.sleep(60)  # Try again in 1 minute

        else:
            msg = 'Serial Port ' + str(ser.port) + ' ' + str(ser.baudrate) + ' seems to be free to use'
            debug_msg(msg)
            ser.open()      #Opens SerialPort
            break

    # print port open or closed and set Text Mode for reading
    if ser.is_open:
        debug_msg('Openned: ' + str(ser.name) + ", baud: "+str(ser.baudrate))        # .name is the port connection
        debug_msg('Setting SMS message format as text mode')
        at_command('AT+CMGF=1')


#Function Ends Here


""" --------------------------------------
    Read from the Serial Port
--------------------------------------"""
def serial_read(search='OK', mytimeout=2, length=10):
    
    ret = {}
    ret['search'] = search
    ret['read'] = ''
    curr_time = time.time()
    while True:
        holder = ser.read(length)
        ret['read'] += str(holder.decode())
        if search in ret['read']:
            ret['status']="Serial Read Search '"+search+"' Found."
            ret['success']=True
            return ret
        if time.time()-curr_time >= mytimeout:
            ret['status']="Serial Read Search Timed Out."
            ret['success']=False
            return ret


""" --------------------------------------
    Read all Messages into a List of dictionaries
-------------------------------------- """
def read_all(output='list'):

    debug_msg('Reading All messages in bulk')
    data = at_command('AT+CMGL="ALL"', ok='OK', timeout=10, length=1000)

    if output == 'raw':
        return data['read']

    mylist = parse_all_messages(data['read'])

    return mylist

# END Function


""" ------------------------------------------

    Use AT Command to Read, Delete Message by ID

    arg string ID number in string form
    OR
    arg list List of IDs

    return dictionary

---------------------------------------------"""
def action_by_ID(action, i):
    
    global AT_COMMAND

    if action == 'read':
        action_text='Reading'
        at_cmd='AT+'+AT_COMMAND['read']+'='
        at_search=AT_COMMAND['read']

    elif action == 'delete':
        action_text='Deleting'
        at_cmd='AT+'+AT_COMMAND['delete']+'='
        at_search=AT_COMMAND['delete']

    if type(i) is str:
        debug_msg(action_text+' ID '+i )
        ids = [i]
    elif type(i) is list:
        debug_msg(action_text+' IDs '+' '.join(i) )
        ids = i

    count=0
    bulk = ''

    for item in ids:
        ret = at_command(at_cmd+item, ok='OK', timeout=3, length=100)
        bulk += ret['read']

    # debug_msg("AT Command Resonse: "+bulk)

    if action == 'read':
        if not re.search('(?i)error', bulk, re.IGNORECASE):
            data = search_for_messages(bulk, at_search)

            if not data:
                data = "Message ID "+i+" does not exist"
        else:
            data = "Error: "+bulk

    elif action == 'delete':
        if not re.search('(?i)error', bulk, re.IGNORECASE):
            data = "Success. Deleted IDs "+' '.join(ids)
        else:
            data = "Error: Error Trying to Delete.\n"+bulk
   
    return data

# END Function



""" ---------------------------------------------

    Parse bulk read raw sms messages recieved into
    a nice array of messages.
    Raw messages must have been read by at_command
    AT+CMGL="ALL"

    arg string Raw sms messages separated by linefeeds

    return a list of dictionaries arrays

-------------------------------------------------- """
def parse_all_messages(bulk_msgs, msg_separator='^\\+CMGL:'):

    debug_msg('parse_all_messages: Parsing a string of bulk messages into a list')

    pointer = 0
    result=[]
    ids=[]
    item={}

    txt = bulk_msgs.split('\n')
    count=0

    debug_msg("Lines being read: "+str(len(txt)))
    debug_msg("Ids Found:\n", False)
    #debug_msg(msgstring)
    
    for line in txt:
        count += 1   # count the lines
        # debug_msg("l", False)
        part_line=re.search(msg_separator, str(line))
        if len(line) > 0 and part_line:
            
            # if dict is not empty
            if item:
                result.append(item)
                item={}
                item["msg"]=''

            # process the details of the message
            parts = [x.strip() for x in line.split(",")]
            i = [y.strip() for y in parts[0].split(" ")]
            item["id"] = i[1].strip("\"")
            item["read_status"]=parts[1].strip("\"")
            item["from"] = parts[2].strip("\"")
            # strip the +1 at start if any
            if item['from'][:2] == '+1':
                item['from'] = item['from'][2:]
            # date is YY/MM/DD and Time is UTC 24:24:00+00
            # sometimes the UTC time has a minus (-) instead of a (+)
            parts[5] = parts[5].replace('-','+')
            dt = parts[4].strip("\"") + ' ' +parts[5].strip("\"").split('+')[0]
            #debug_msg(" - Converting UTC date ["+dt+"] to EST")
            dateobj = datetime.datetime.strptime(dt.strip(), '%y/%m/%d %H:%M:%S')
            # Set Time zone from UTC to EST
            from_tz = tz.gettz('UTC')
            to_tz = tz.gettz('US/Eastern')
            dateobj = dateobj.replace(tzinfo=from_tz)
            dateobj = dateobj.astimezone(to_tz)
            # debug_msg(" - New Local Datetime: "+str(dateobj))
            prettydate = dateobj.strftime('%b %d %Y %I:%M %p')
            # debug_msg(" - Stored Date as: "+prettydate)
            item["datetime"] = prettydate
            debug_msg(item['id']+' ', False)
            pointer = 1  # the next line is the message
            msg_counter = 0 # reset message line counter

        elif len(line) > 0 and pointer == 1:
            msg_counter += 1
            # debug_msg("m", False)
            # remove \r and multiple spaces in line
            tmpstr=re.sub('\r','',line)
            tmpstr=re.sub(' +',' ',tmpstr)
            
            # if the last line is OK then dont save last line (its AT Response)
            if not re.search('^OK', tmpstr) and len(tmpstr) > 0 and count < len(txt):
                # if item[msg] is not empty then add a \n
                if item.get("msg"):
                    item["msg"] = item["msg"]+"\n"+tmpstr.strip()
                else:
                    item["msg"] = tmpstr.strip()
            else:
                result.append(item)
                pointer = 0

    debug_msg("\nTotal Messages Read: "+ str(len(result))+"\n")

    result = sort_msgs_by_date(result)

    return result

#End Function


""" ----------------------------------------------------

    Search a list by regex and return all the matches

    arg list List to search
    arg string Regex string to search for.

    return list

---------------------------------------------------------"""
def search_list(mylist, search_str):

    if not mylist or not search_str:
        err = "Error: list or search is empty"
        debug_msg(err)
        return [err]

    new_list=[]

    debug_msg("Searching for "+search_str+" ... ", False)

    for item in mylist:
        if re.search(search_str, item['from']):
            new_list.append(item)
        elif re.search(search_str, item['msg'], re.IGNORECASE):
            new_list.append(item)
        elif re.search(search_str, item['datetime'], re.IGNORECASE):
            new_list.append(item)

    debug_msg(str(len(new_list))+" records found")

    if new_list:
        # make a new list of IDs
        ids = get_key_values('id', new_list)
        # Remove any duplicate IDs in the saved id list
        # ids = list(set(ids))
        ids = list(ids for ids,_ in itertools.groupby(ids))

        # Dont save unless the list has values
        if ids:
            save_list(ids)
            str1 = ' '.join(ids)
            debug_msg("IDs ["+str1+"]")
    
    return new_list 

# END Function



""" ----------------------------------------------------

    Search a list for matching IDS

    arg list List to search
    arg list List of IDs to search for.

    return list

---------------------------------------------------- """
def get_messages_by_ids(mylist, myids):

    if not mylist or not myids:
        err = "Error: list is empty"
        debug_msg(err)
        return [err]

    new_list=[]

    debug_msg("Searching Lists for matching IDs ...", False)

    for myid in myids:
        for item in mylist:
            if re.search(str(myid), item['id']):
                new_list.append(item)
                break

    debug_msg(str(len(new_list))+" records found ["+' '.join(new_list[0])+"]")

    from pprint import pprint

    print ("new_list is "+str(type(new_list)))
    pprint(new_list)
    sys.exit(0)

    return new_list 

# END Function

""" ----------------------------------------------------
    Get Messages from shortcode (numbers from 4-6 digit)
---------------------------------------------------- """
def get_shortcodes(mylist):

    debug_msg("Searching messages with mobiles outside 7-11 Digits (shortcodes)...")

    new_list= []

    for item in mylist:
        if len(item['from']) <7 or len(item['from']) >10:
            new_list.append(item)
    
    return new_list

# END Function



""" ----------------------------------------------------
     Parse raw read by id sms messages

     arg string Raw sms messages separated by line
     arg string Raw string to search for 

      The raw message looks like...

     When reading all:
        +CMGL: 2,"REC READ","+17056715441",,"18/11/24,06:25:31+00"
        Oopsss sorry   again   Mike 
     
     When Reading One Msg:
        AT+CMGR=51
        +CMGR: "REC READ","+17059292110",,"19/02/15,14:56:21+00"
        Hey you. Listen to me!

     at_search could be "CMGD" or "CMGR"

     return list of dictionary messages
---------------------------------------------------- """
def search_for_messages(bulk, at_search='CMGR'):

    str_search=''
    if at_search == 'CMGR':
        str_search = 'Read'

    debug_msg('Gathering Messages ...')

    pointer=1
    counter=0
    result=[]
    item={}
    id_search="AT+"+at_search+"="
    detail_search="+"+at_search+":"
    lines = bulk.split('\n') 

    numlines = len(lines)
    debug_msg("Number of lines being read: "+str(numlines))
    #debug_msg(msgstring)
    
    for line in lines:

        counter += 1

        # string[:6] Returns from the beginning to pos 6
        # First look for the ID number
        if pointer == 1 and len(line) > 0 and id_search in line[:len(id_search)]:

            # if dict is not empty
            if item:
                debug_msg("Saving Message Data "+json.dumps(item))
                result.append(item)
                item={}
                item["msg"]=''

            parts = [x.strip() for x in line.split("=")]
            item["id"] = parts[1].strip()
            debug_msg("Found line "+str(counter)+" has an ID "+item["id"]+" -> "+line.strip())
            pointer = 2
        elif pointer == 2 and len(line) > 0 and detail_search in line[:len(detail_search)]:
            parts = [x.strip() for x in line.split(",")]
            #i = [y.strip() for y in parts[0].split(" ")]
            item["from"] = parts[1].strip("\"")
            # strip the +1 at start if any
            if item['from'][:2] == '+1':
                item['from'] = item['from'][2:]
            # date is YY/MM/DD and Time is UTC 24:24:00+00
            dt = parts[3].strip("\"") + ' ' +parts[4].strip("\"").split('+')[0]
            #debug_msg(" - Converting UTC date ["+dt+"] to EST")
            dateobj = datetime.datetime.strptime(dt, '%y/%m/%d %H:%M:%S')
            # Set Time zone from UTC to EST
            from_tz = tz.gettz('UTC')
            to_tz = tz.gettz('US/Eastern')
            dateobj = dateobj.replace(tzinfo=from_tz)
            dateobj = dateobj.astimezone(to_tz)
            # debug_msg(" - New Local Datetime: "+str(dateobj))
            prettydate = dateobj.strftime('%b %d %Y %I:%M %p')
            # debug_msg(" - Stored Date as: "+prettydate)
            item["datetime"] = prettydate
            pointer = 3
            #debug_msg("Adding Details to List -> "+item["datetime"])

        elif pointer == 3 and len(line) > 0:
            # debug_msg("Reading Message ID: "+item['id'])
            tmpstr=re.sub('\r','',line)
            # convert 2 or more spaces to 1
            tmpstr=re.sub(' +',' ',tmpstr)
            # if the last line is OK then dont save last line (its AT Response)
            if not re.search('^OK', tmpstr) and len(tmpstr) > 0 and counter < numlines:
                # if item[msg] is not empty then add a \n
                if item.get("msg"):
                    item["msg"] = item["msg"]+"\n"+tmpstr.strip()
                else:
                    item["msg"] = tmpstr.strip()
                #debug_msg("line: "+str(counter)+' -->'+item['msg']+'<')

            else:
                #result.append(item)
                pointer = 1
                #debug_msg("Saving Message Data "+json.dumps(item))

        #debug_msg("Pointer = "+str(pointer))

    if item:
        debug_msg("Saving Message Data "+json.dumps(item))
        result.append(item)

    #debug_msg("Messages Gathered "+str(json.dumps(result)))

    result = sort_msgs_by_date(result)

    debug_msg("Gathered: "+str(len(result)))

    return result

#END Function

""" ----------------------------------------------------
    Sort a List of dictionary messages by date
---------------------------------------------------- """
def sort_msgs_by_date(result):

    new = sorted(result,key=lambda x : time.strptime(x['datetime'],"%b %d %Y %I:%M %p"))

    return new


"""---------------------------------------------

    Get the last N messages from a list

    arg list List of Messages
    arg int Integer of last messages from list to retrieve

    return list

------------------------------------------------"""
def get_last_messages(mylist, num=1):

    if not mylist:
        return []
    if num < 1:
        return []
    if num > len(mylist):
        return []

    # negate the number so we can get the last of the list
    num = num*-1

    return mylist[num:]

# END Function

""" ----------------------------------------------------

    Get a list of Key values for a given key from a list

    arg string list of key names
    arg string list of dictionaries to search

    return list of key values

---------------------------------------------------- """
def get_key_list(mykeys, mylist):

    debug_msg("Getting values for keys ("+','.join(mykeys)+") only")
    
    key_list = get_key_values(mykeys, mylist)

    if not key_list:
        msg = "Keys ("+','.join(mykeys)+") are not found or invalid"
        output_close(msg)
    else:
        debug_msg("Removing Duplicates in list ... Now size: ", False)
        key_list = list(key_list for key_list,_ in itertools.groupby(key_list))
        #key_list = list(set(key_list))
        debug_msg(str(len(key_list)))
    
    return key_list

# END Function


""" ----------------------------------------------------

    Get a list of Key values for a given key

    arg string key 
    arg string list of dictionaries to search

    return list of nested list of values

---------------------------------------------------- """
def get_key_values(mykeys, mylist):

    new_dict={}
    new_list=[]

    if type(mykeys) is str:
        for item in mylist:
            #debug("Searching list for key :"+mykeys)
            if mykeys and mykeys in item:
                #debug(" - Adding : "+item[mykeys])
                new_list.append(item[mykeys])

    if type(mykeys) is list:
        debug_msg("get_key_values: Adding a dictionary of items to a list")
        for item in mylist:
            tmp_dict={}
            for k in mykeys:
                if k in item:
                    #debug_msg("get_key_values: appending "+item[k]+" "+','.join(item)+" to tmp_list")
                    debug_msg("Adding "+ k +":"+ item[k])
                    tmp_dict[k]=item[k]
            new_list.append(tmp_dict)

        #new_list = sorted(new_list, key=lambda k: k['id'])
        if 'datetime' in mykeys:
            new_list = sorted(new_list, key=itemgetter('datetime'))
        elif 'id' in mykeys:
            new_list = sorted(new_list, key=itemgetter('id'))
        else:
            new_list = sorted(new_list, key=itemgetter(mykeys[0]))
        #new_list.sort(key=itemgetter(0))

    #print(*new_list, sep = "\n")
    #print('\n'.join(map(str, new_list)))

    return new_list
# End Function


""" ----------------------------------------------------  
    Send an AT Command to serial and wait for response
---------------------------------------------------- """
def at_command(msg, ok='OK', timeout=2, length=10):

    if ser.is_open:
        save_at_command(msg)

        # t0 = time.time()
        #while True:
        #ser.write(msg+chr(13))
        ser.write(str.encode(msg+chr(13)))
        ret = serial_read(ok, timeout, length)

        if not ret['success']:
            debug_msg('AT Command Failed: '+msg)
            debug_msg(""+ret['status'])
            debug_msg("Error Code: "+error_code(ret['read']))
            debug_msg("Response: \n"+ret['read'])

        return ret


# Function Ends Here


""" ----------------------------------------------------
    Look up an error code in a file list and display description
---------------------------------------------------- """
def error_code(mystr):

    global errorcodes

    if not errorcodes: 
        if not os.path.isfile(errorCodesFile):
            debug_msg(" - File: "+errorCodesFile+" does not exist")
            close_serial_connection()

        with open(errorCodesFile, 'r') as f:
            errorcodes = ast.literal_eval(f.read())

    txt = mystr.split('\n')
    for line in txt:
        if 'ERROR' and re.findall('\d+',line):
            #debug_msg("Error Found: "+line)
            err=re.findall('\d+',line)
            for key,value in errorcodes: 
                if key in err:
                    return value
                    break
    return "(unknown)"
#Function Ends Here


""" ----------------------------------------------------
    Close and end program
---------------------------------------------------- """
def close_serial_connection():

    global ser

    debug_msg('Closing Serial Connection...', False)
    if ser.is_open:  
        ser.close()   # close serial port
        if ser.is_open:
            debug_msg(' [ Failed ]')
    else:
        debug_msg(' Not open [ Success ]')

    debug_msg('[ Success ]')

# END Function



""" --------------------------------------
    Print Messages to the screen and logfile
-------------------------------------- """
def debug_msg(mystr, linefeed = True):

    mystr = str(mystr)
    if debug:
        sys.stdout.write(mystr)

        if linefeed:
           sys.stdout.write("\n")

        sys.stdout.flush()

    logging.debug(get_date()+" ::: "+mystr)
# END Function


""" --------------------------------------

    Send Output to console as json or text then exit

    arg list List of Dictionaries
    or
    arg list with 1 String arg
    or 
    arg string Sting status of query

------------------------------------------"""
def output_close(myobject):

    success = '{"status":"success","result":'
    error = '{"status":"error","result":'
    myoutput = "output_close: arg is not type str or list"

    global args

    if args['text']:
        if type(myobject) is list and type(myobject[0]) is dict:
            # we have no choice but to force json
            myoutput = json.dumps(myobject, indent=4)
        elif type(myobject) is list and type(myobject[0]) is list:
            myoutput = ''
            for item in myobject:
                if len(item) > 1:
                    myoutput += ','.join(item)+"\n"
                else:
                    myoutput += item[0]+' '
            myoutput = myoutput[:-1]
        elif type(myobject) is list:
            # we have no choice but to force json
            myoutput = ' '.join(myobject)
        elif type(myobject) is dict:
            myoutput = json.dumps(myobject, indent=4)
        elif type(myobject) is str:
            myoutput = myobject

    else:
        if type(myobject) is list:
            if type(myobject[0]) is str and len(myobject) == 1:
                if re.search("(?i)^error", myobject[0], re.IGNORECASE):
                    myoutput = error+'"'+myobject[0]+'"}'
                else:
                    myoutput = success+'"'+myobject[0]+'"}'
            else:
                data = json.dumps(myobject, indent=4)
                myoutput = success+data+'}'
        elif type(myobject) is str:
            if re.search("(?i)^error", myobject, re.IGNORECASE):
                myoutput = error+'"'+myobject+'"}'
            else:
                myoutput = success+'"'+myobject+'"}'
        else:
            myoutput = myobject

    print (myoutput)
    
    close_serial_connection()

    if not error:
        sys.exit(0)
    else:
        sys.exit(1)
# END Function



""" --------------------------------------
    Save AT command to a File
-------------------------------------- """
def save_at_command(mystr):
    if mystr.find('AT+') > -1:
        global atfile
        with open(atfile, "a") as f:
            f.write(mystr+"\n")
# END Function


""" --------------------------------------
    Save data to a File
-------------------------------------- """
def save_date(myfile):
    format = "%a %b %d %H:%M:%S"
    d = datetime.datetime.today().strftime(format)
    with open(myfile, "a") as f:
            f.write("------------------------------\n"+d+"\n------------------------------\n")
# END Function


""" --------------------------------------
    Save a list of strings for later reading by this script
-------------------------------------- """
def save_list(mylist, myfile=''):

    debug_msg("Saving List to file")

    if not mylist:
        debug_msg("There were no IDs found. Save Aborted.")
        return
    
    # from pprint import pprint

    # debug_msg("is Dict mylist? "+str(type(mylist)))
    # pprint(mylist[2])

    # debug_msg("is List mylist0? "+str(type(mylist[0])))


    # check if first element in list is multidemetional ie. [ [1,2,3], [4,5,6] ]
    if isinstance(mylist[0], dict):
        debug_msg("Getting list of IDs from list of dictionaries")
        # make a new list of only IDs
        ids = get_key_values('id', mylist)

    else:
        #debug_msg("List given is "+str(type(mylist)))
        ids = mylist

    # pprint(mylist[2])
    # pprint(ids)
    # sys.exit(0)
    # #pprint(globals())
    #debug_msg(','.join(ids) +"\n")
    #print str(vars(ids))

    # Dont save unless the list has values
    if not ids:
        debug_msg("There were no IDs found. Save Aborted.")
        return

    debug_msg("IDs Found: "+str(len(ids)) + ' ' + str(type(ids)))

    if not myfile:
        global lastReadIdsFile
        myfile = lastReadIdsFile
    with open(myfile, "w") as f:
        f.write(','.join(ids) +"\n")

    debug_msg( str(len(ids)) + " lines saved to: "+str(myfile))
# END Function


""" --------------------------------------
    Read a list of strings from a file into a list
-------------------------------------- """
def load_list(myfile=''):

    if not myfile:
        global lastReadIdsFile
        myfile = lastReadIdsFile

    debug_msg("Loading list of IDs from file: "+str(myfile))

    mylist=[]
    if not os.path.isfile(myfile):
        debug_msg("Error: "+myfile+" does not exist.")
        return []

    else:
        with open(myfile, "r") as f:
            for line in f:
                tmplist = line.split(",")
                mylist = [sub.replace('\r', '').replace('\n', '') for sub in tmplist]
                #record.append()
                #mylist.append(tmp_list)
                #record=[]

    debug_msg("Loaded "+str(len(mylist))+" IDs")

    return mylist
# END Function


""" ======================================================

    START

========================================================== """

""" --------------------------------------
    Usage
--------------------------------------"""
s="""
Files
-----
        Log File:       {log}
        Quectel E25 Chipset Error Codes:
                        {error}
Author
------
        Feb 22 2019
        Michael Connors
        daddyfix@outlook.com
                
""".format( log=logfile,
            error=errorCodesFile
)
parser = argparse.ArgumentParser(
                description='Script to read MMS/SMS Messages',
                formatter_class=argparse.RawTextHelpFormatter,
                epilog=(s)
)

read_help = """

Read / Delete / Search SMS OPTIONS
----------------------------------

"""
#-----------------------------------------------------------
# Read SMS Recieved
# ----------------------------------------------------------
parser.add_argument('-ra','--readall', action='store_true', help="Read all the SMS messages recieved", required=False)
parser.add_argument('-raw','--readallraw', action='store_true', help="Read all the SMS message and display raw output", required=False)
parser.add_argument('-r','--readn', type=str, help="Read SMS by ID. IDs can be separated by comma (ie. 20,25,30)", required=False)
parser.add_argument('-s','--search', type=str, help="Search 'from', 'message', and 'datetime' fields in messages. Regex can my used.\nFYI: '(?i)' in regex expression will turn off case sensitive", required=False)
parser.add_argument('-k','--key', action='append', type=str, help="Return key fields only from Search\nie. -s 'hello' -k 'from' -k 'datetime'.\nSearch returns only key fields\nSort is done on the first key specified", required=False)
parser.add_argument('-rl','--readlastn', nargs='?', type=int, default=-1, help="Display the last N sms messages.\nDefault: Last 1 message", required=False)
parser.add_argument('-ls','--lastsearch', action='store_true', help="Show the messages made with the last search command", required=False)
parser.add_argument('-sl','--showlist', action='store_true', help="Show the IDs of the messages made with the last command", required=False)
parser.add_argument('--shortcodes', action='store_true', help="Show all messages from shortcode phone numbers not 7-11 digits", required=False)
parser.add_argument('-DEL','--deleten', type=str, help="Delete SMS by ID. IDs can be separated by comma (ie. 20,25,30)", required=False)
parser.add_argument('-DALL','--deleteall', action='store_true', help="Delete all the SMS messages recieved", required=False)
parser.add_argument('-DLIST','--deletelist', action='store_true', help="Delete ALL the message IDs in --lastsearch list", required=False)
parser.add_argument('-DL','--deletelastn', nargs='?', type=int, default=-1, help="Delete the last N messages by date ONLY (Ascending)", required=False)

#-----------------------------------------------------------
# Regular Args
#-----------------------------------------------------------
mypaths = """
Default File Path: {files}
Image File Path: {images}
Files must be in either of the above directories
unless otherwise specified.
""".format(files=modem_files_path,
           images=imagepath
)
parser.add_argument('-p','--path', help=mypaths, required=False)
parser.add_argument('-b','--baudrate', help='Default: '+default_baudrate, required=False)
parser.add_argument('-o','--port', help='Default: '+default_port, required=False)
parser.add_argument('-d','--debug', action='store_true', help='Default: '+str(debug), required=False)
parser.add_argument('--json', action='store_true', help='Output results as json [Default]', required=False)
parser.add_argument('--text', action='store_true', help='Output results as text', required=False)


# Add all the Command Line args to array(list)
args = vars(parser.parse_args())

""" --------------------------------------------
    If no arguments have been passed
------------------------------------------------"""
if not len(sys.argv) > 1:
    parser.print_help()
    sys.exit()
""" --------------------------------------------
    If the only arg is debug
------------------------------------------------"""
if len(sys.argv) == 2 and sys.argv[1] == '-d':
    parser.print_help()
    sys.exit()
""" --------------------------------------------
    Cannot have 'key' without ...
------------------------------------------------"""
if args['key']:
    err = 4
    if not args['search']:
        err -= 1
    if not args['readall']:
        err -= 1
    if not args['readn']:
        err -= 1
    if args['readlastn'] == -1:
        err -= 1
    
    if err == 0:
        print ("Cannot have --key without --search, --readall, --readlastn, or --readn")
        sys.exit()


""" ------------------------------------------
    Show the last saved IDs list file
----------------------------------------------"""
if args['showlist']:
    mylist = load_list()
    if args['text']:
        print (' '.join(mylist))
    else:
        import json
        print (json.dumps(mylist))
    # strlist = ''
    # for s in mylist:
    #     strlist+=" ".join(map(str, s))
    # debug_msg("Last read or search IDs\n"+strlist)
    # if not strlist:
    #     strlist = "empty"
    # print strlist
    sys.exit()


""" ------------------------------------------
    Set the Modem Connection Defaults
----------------------------------------------"""
if not args['baudrate']:
    args['baudrate'] = default_baudrate
if not args['port']:
    args['port'] = default_port
if not args['text'] and not args['json']:
    args['json'] = True
if args['debug']:
    debug = True



# ---------------------------- START ----------------------------


"""
Save Date to log files
"""
save_date(logfile)
save_date(atfile)


debug_msg( "Args Given: "+str(args)[1:-1] )
#debug_msg( "Action List: ["+' '.join(SMSAction)+']' )

"""

Call the Serial Initilization

"""
init_serial()


""" ====================================================

    Operations where pre-read all messages is
    ** NOT ** Required

========================================================"""

""" ---------------------------------
    Read a message by ID
----------------------------------"""
if args['readn']:
    debug_msg("Reading SMS Message ID "+str(args['readn']))

    read_list = str(args['readn']).split(",")

    message_list = action_by_ID('read', read_list)

    if args['key']:
        message_list = get_key_list(args['key'], message_list)

    output_close(message_list)

""" ---------------------------------
    Read all message and output raw string
----------------------------------"""
if args['readallraw']:

    raw_messages = read_all('raw')
    if not raw_messages:
        msg = "empty"
        output_close(msg)

    output_close(raw_messages, 'raw')

""" ---------------------------------
    Delete All Messages
-------------------------------------"""
if args['deleteall']:

    debug_msg('Deleting All SMS Messages ...')
    # Get a list of all the messages we are deleting
    ret = at_command('AT+CMGD=1,4', ok='OK', timeout=2, length=30)

    result = read_all()

    if len(result) == 0:
        msg = "Deleted all Messages [ Success ] "
    else:
        msg = "Error: Delete all Messages [ Failed ] "+json.dumps(result)

    output_close(msg)


""" ---------------------------------
    Delete ONE Message By ID
-------------------------------------"""
if args['deleten']:

    debug_msg("Deleting SMS Message ID "+str(args['deleten']))

    delete_list = str(args['deleten']).split(",")

    result = action_by_ID('delete', delete_list)
    
    output_close(result)


""" ---------------------------------
    Delete ALL Messages in the last saved list
-------------------------------------"""
if args['deletelist']:

    debug_msg("Deleting messages in last search history")

    loaded_ids = load_list()
    if not loaded_ids:
        msg = "Error: The last search history is empty."
        output_close(msg)

    debug_msg("Deleteing IDs: "+' '.join(loaded_ids))

    result = action_by_ID('delete', loaded_ids)

    # clear list
    if not re.search('(?i)^error', result, re.IGNORECASE):
        save_list([])

    output_close(result)
        


""" ====================================================

    Operations where pre-read all messages
    ** IS ** required

========================================================"""

""" ---------------------------------
    Read a message by ID
----------------------------------"""
message_list = read_all()




""" ---------------------------------
    Read all messages
----------------------------------"""
if args['readall']:

    if not message_list:
        msg = "empty"
        output_close(msg)

    if args['shortcodes']:
        message_list = get_shortcodes(message_list)
        if not message_list:
            save_list([])
            output_close("empty")
        else:
            save_list(ids)

    if args['key']:
        message_list = get_key_list(args['key'], message_list)

    output_close(message_list)


""" ---------------------------------
    Read all shortcoded messages 
----------------------------------"""
if args['shortcodes']:

    if not message_list:
        msg = "empty"
        output_close(msg)

    message_list = get_shortcodes(message_list)
    if not message_list:
        save_list([])
        output_close("empty")
    else:
        save_list(message_list)

    ids = get_key_list(['id'], message_list)

    output_close(ids)

""" ---------------------------------
    Search All Messages
----------------------------------"""
if args['search']:

    debug_msg("Searching All Messages for "+args['search'])

    message_list = search_list(message_list, args['search'])

    if not message_list:
        msg = "empty"
        output_close(msg)

    if args['shortcodes']:
        message_list = get_shortcodes(message_list)
        if not message_list:
            save_list([])
            output_close("empty")
        # make a new list of IDs
        ids = get_key_values('id', message_list)
        # Dont save unless the list has values
        if ids:
            save_list(ids)

    if args['key']:
        message_list = get_key_list(args['key'], message_list)

    output_close(message_list)


""" ---------------------------------
    Read the Last N Messages by date

    if arg NOT given by default it is -1
    if arg given with a num then its the num
    if arg give without num then its None
----------------------------------"""
if args['readlastn'] is None or args['readlastn'] > -1:

    if args['readlastn'] is None:
        args['readlastn'] = 1

    debug_msg("Reading Last "+str(args['readlastn'])+" Messages")

    new_list = get_last_messages(message_list, args['readlastn'])

    if not new_list:
        msg = "Error: There are "+str(len(message_list))+" messages and you asked to get the last "+str(args['readlastn'])+" messages."
        output_close(msg)

    # make a new list of IDs
    ids = get_key_values('id', new_list)

    # Dont save unless the list has values
    if ids:
        save_list(ids)

    if args['key']:
        new_list = get_key_list(args['key'], new_list)
        
    output_close(new_list)


""" ---------------------------------
    Show the Results from the last search
-------------------------------------"""
if args['lastsearch']:

    debug_msg("Getting Saved List") 
    loaded_ids = load_list()
    if not loaded_ids:
        msg = "Error: The last search history is empty."
        output_close(msg)

    new_list = get_messages_by_ids(message_list, loaded_ids)

    if not new_list:
        msg = "Error: The last saved list has no matches in the current list"
        output_close(msg)
        
    output_close(new_list)


""" ---------------------------------
    Delete the Last N Messages by date

    if arg NOT given by default it is -1
    if arg given with a num then its the num
    if arg give without num then its None
----------------------------------"""
if args['deletelastn'] is None or args['deletelastn'] > -1:

    if args['deletelastn'] is None:
        args['deletelastn'] = 1

    debug_msg("Deleting Last "+str(args['deletelastn'])+" Messages")

    delete_list = get_last_messages(message_list, args['deletelastn'])

    if not delete_list:
        msg = "Error: There are "+str(len(message_list))+" messages and you asked to get the last "+str(arg['readlastn']+" messages.")
        output_close(msg)

    ids = get_key_values('id', delete_list)

    result = action_by_ID('delete', ids)

    output_close(result)




