mport sys;
import os;
import getopt;
import pexpect;
import re;
import subprocess;
import hashlib;

errorList = []
thereList = []


#####################################################################################
#
#       License/Rights:  AT&T Labs
#
#       Author: Jesse Strivelli
#
#       Functionality: This script takes IOS files copys them to the flash of routers
#                      and switches and then sets up a boot which priotizes them into
#                      previously existing order with the boot we specify in the usage
#                      this script will only work on the device it was intended to be 
#                      for. Trying this script out will not work on other devices
#
#
#       Usage: python script.py <device 1> ... <device N> <IOS File>
#
#####################################################################################




#
## This method is called to check the return status of a SCP 
#
def SCPTest(deviceList, IOSfile, path):
  SCPList = []
  for device in deviceList:
    status = os.system("scp " + str(path) + " " + str(device) + ":/flash:" + str(IOSfile))
    if status == 0:
        SCPList.append(device)
    else:
        errorList.append(str(device) + "\tDevice protocol error- Can't reach Device")

  return SCPList;



#
## This method Compare the version of the config file to the version 
## of the device and append to error list if not compatible
## This method does not support Juniper
#        
def versionTest(deviceList, IOSfile):
  versionList = []
  for device in deviceList:
      command = "ssh " + device + " show version | grep \"System image file\""
      #this next line is used to standard output our command into a string

      try:
        result = subprocess.check_output(command, shell=True)
      except:
        errorList.append(device + "\tCan't reach device")
        continue
      IOSfile = IOSfile[:IOSfile.find('-')]
      #lowercase both to exlucde case sensitivity
      IOSfile.lower()
      result.lower()
      if result.find(IOSfile) != -1:
          versionList.append(device)
      else:
          errorList.append(device + "\tIOS version for file is different than the device")

  return versionList


#
## this class is used to sort the list of files on the device which we will use in the sizeTest method
#
class ConfigFile:
    def __init__(self, name, size):
        self.name = name
        self.size = size

#
## method to check if the file size is too large for the device
## if file is too big we send a report of the 4 largest files on the device
## this includes the name of the file and the size of the file
#
def sizeTest(deviceList, IOSfile, path):
  sizeList = []
  for device in deviceList:
      command = "ssh " + device + " show flash:"
      result = subprocess.check_output(command, shell=True)
      #we are splitting up the last line of show flash so we can access the first part of it to get the deviceSize
      a = result.split("\n")
      lastLine = a[len(a) -2].split()
      #getting file size using the os package
      fileSize = os.stat(path).st_size
      #this is getting the deviceSize
      deviceSize = int(lastLine[0])
      #if the fileSize is greater than deviceSize we want to print out the four largest files on the device
      if fileSize > deviceSize:
          sizeList = []
          #trimming down the length of the string so we can iterate through properly with getting an index out of bounds error
          a = a[1:len(a)-3]
          for line in a:
                  #split each line into tokens which are seperated by and not including the spaces
                  lineTokens = line.split()
                  #add the length of the file to sizeList
                  #sizeList.append("Size: " + lineTokens[1])
                  #If the name matchs IOSfile then it is already on the device
                  b = ConfigFile(lineTokens[len(lineTokens)-1], int(lineTokens[1]))
                  sizeList.append(b)

          #sort the size list
          sizeList.sort(key = lambda x: x.size, reverse=True)
          newList = sorted(sizeList, key = lambda x: x.size, reverse=True)
          stringOutput = ""
          #we only want to print the first 4 elements because they are the 4 largest
          for c in newList[:4]:
                  stringOutput +=  "\tName: " +  c.name + "\t\tSize: " + str(c.size) + " bytes\n"
          stringOutput += "\n\tDevice space: " + str(deviceSize) + " bytes \tFile Size: " + str(fileSize) + " bytes\n"
          errorList.append(device + "\tFile is too large to fit on device - Report of 4 largest files on device below\n" + stringOutput)
      else:
          sizeList.append(device)

  return sizeList



#
## This md5 check is used to check and verifiy that scp has worked
## Md5 gives a hash of a file similar to a dictionary so in this method the
## two devices have to have matching hashes for the file for this method to return true
#
def md5Check(deviceList, IOSfile, path):
  md5List = []
  for device in deviceList:
      print "Running an MD5 check on " + device
      #this first segment is to obtain the hash for the file on the device this script is sitting on
      hash_md5 = hashlib.md5()
      with open(path, "rb") as f:
          for chunk in iter(lambda: f.read(4096), b""):
              hash_md5.update(chunk)
      linuxHash = hash_md5.hexdigest()
      print linuxHash
      #this command checks to see if the hash matches or is even on the device scp the file to
      if os.system("ssh " + device + " verify /md5 flash:" + IOSfile + " | grep " + linuxHash) == 0:
          md5List.append(device)
      else:
          errorList.append(device +  "\tMd5 Check failed for this device")

  return md5List


#
## This method checks to see if the file is already on the device
#
def deviceFileCheck(deviceList, IOSfile):
  checkList = []
  for device in deviceList:
    if os.system("ssh " + device + " show version | grep \"bootflash\"") == 0:
        IOSfile = "/bootflash/" + IOSfile
    if os.system("ssh " + device + " show flash: | grep " + IOSfile) == 0:
        thereList.append(device)
        print "The IOS file is already on " + device + ". We will skip to the md5 test"
    else:
        checkList.append(device)
  return checkList


#
## This method is the last part of the script. It boots the IOS as top priority
## It then writes the IOS file to NVRAM and reloads each device
#
def boot(deviceList, IOSfile):
  bootList = []
  for device in deviceList:
    #This first part I need to save the existing configs into a list
    command = "ssh " + device + " \"show run | include boot sys\""
    result = subprocess.check_output(command, shell=True)
    currConfigs = result.split("\n")
    #trimmming the string because the last line is a blank line
    currConfigs = currConfigs[:len(currConfigs)-1]
    #We need to work using synchronous programming which is why we are using pexpect


    child = pexpect.spawn('ssh ' + device)
    child.timeout = 4

    a = bootUpdate(device, IOSfile, currConfigs, child)
    if a == -1:
      continue
    b = bootWrite(device, child)
    if b == -1:
      continue
    c = bootReload(device, child)
    if c == 0:
      bootList.append(device + "\tSuccess")

  return bootList


############################

def bootUpdate(device, IOSfile, currConfigs, child):
    try:
        print str(device) + "#"
        child.expect('#')
    except pexpect.TIMEOUT:
        errorList.append(device + "\tCould not ssh onto during boot")
        return -1

    child.sendline('config t')
    try:
        child.expect('config')
        print str(device) + "(config)#"
    except pexpect.TIMEOUT:
        errorList.append(device + "\tCould not get into config mode during boot")
        return -1


    print "Removing existing boot..."
    child.sendline('no boot sys')
    try:
        child.expect('config')
    except pexpect.TIMEOUT:
        errorList.append(device + "\tCouldn't Erase current boots")
        return -1


    if os.system("ssh " + device + " show version | grep \"bootflash\"") == 0:
        print "Putting new boot on .... bootflash " + device
        child.sendline('boot system bootflash:' + IOSfile)
        try:
            child.expect('config')
        except pexpect.TIMEOUT:
            errorList.append(device + "\tCould not load new boot onto " + device)
            return -1
    else:
        print "Putting new boot on .... flash " + device
        child.sendline('boot system flash:' + IOSfile)
        try:
            print "boot system bootflash:"
            child.expect('config')
        except pexpect.TIMEOUT:
            errorList.append(device + "\tCould not load new boot onto " + device)
            return -1

    #put the already existing configs back in the config list
    print "Putting existing boots back onto list"
    for i in currConfigs:
        #for some reason there is a \r at the end of the string that we need to trim off so we can load the proper boot name
        i = i[:len(i) - 1]
        child.sendline(i)
        try:
            child.expect('config')
        except pexpect.TIMEOUT:
            errorList.append(device + "\tCould not load " + i + " to the boot list")
            return -1

    
    #exit config mode
    child.sendline('exit')
    try:
         child.expect('#')
    except pexpect.TIMEOUT:
         errorList.append(device + "\tCould not exit config mode during boot")
         return -1

    child.close
    return 0

########################################

def bootWrite(device, child):

    try:
        child.expect('#')
    except pexpect.TIMEOUT:
        errorList.append(device + "\tCould not ssh onto during boot")
        return -1

    print "Writing the new boot to NVRAM"
    child.sendline('wr')

    try:
         child.expect('[confirm]')
         child.sendline('y')
         print 'Overwrite to NVRAM'
         try:
                child.expect('#')
                print "Good write to NVRAM"
         except pexpect.TIMEOUT:
                errorList.append(device + "\tCould not write config  to NVRAM during boot")
                return -1
    except pexpect.TIMEOUT:
         try:
                child.expect('#')
         except pexpect.TIMEOUT:
                errorList.append(device + "\tCould not write the boot to NVRAM during boot")
                return -1

    child.close
    return 0

    

##########################################

def bootReload(device, child):
    ### The Reload takes a little more time
    child.timeout = 10

    try:
        child.expect('#')
    except pexpect.TIMEOUT:
        errorList.append(device + "\tCould not ssh onto during boot")
        return -1

    print "Reloading " + device
    child.sendline('reload')
    try:
        child.expect('Save?')
        print "System confirm question"
        child.sendline('y')
        try:
                child.expect('Overwrite')
        except pexpect.TIMEOUT:
                errorList.append(device + "\tProblem with Overwriting the NVRAM during reload for " + device)
                return -1
        child.sendline('y')
        try:
                child.expect('Proceed')
        except pexpect.TIMEOUT:
                errorList.append(device + "\tProblem with proceed confirmation during reload during boot")
                return -1
    except pexpect.TIMEOUT:
        try:
                child.expect('Proceed')
        except pexpect.TIMEOUT:
                errorList.append(device + "\tCould not reload during boot")
                return -1

    child.sendline('y')
    child.close

    print "Successful Boot"
    return 0


#
##This method checks to see if the device is a valid device to use else it appends to our error list
#
def isValid(deviceList):
    isValidList = []
    for device in deviceList:
        if os.system("grep " + device + " /etc/hosts") == 0:
                isValidList.append(device)
        else:
                errorList.append(device + "\tis not in our configuration list")
    return isValidList


#
##  This method prints out a readable document of the configuration 
##  report and seperates an error and success list starts  
##  with print of the successlist followed by the errorlist
#
def IOSReport(list1, list2):
    print "------------------------------------------------------------------------------------------"
    print "\t\t\t\tIOS Report"
    print "------------------------------------------------------------------------------------------"
    for b in list1:
        print b
    print "---------------------------"
    print "---------------------------"
    for a in list2:
        print a
    print "------------------------------------------------------------------------------------------"
    print "------------------------------------------------------------------------------------------"

#
## This main method goes through a process of checks to see if the IOS files can be properly
## updated on to devices such as routers and switches
#
def main():

        if len(sys.argv) <= 2:
               print "Usage:"
               print "python script.py <device 1> ... <device N> <IOS File>"
               sys.exit(1)
        #The file is the last argument on the command line
        tfile = sys.argv[len(sys.argv) - 1]
        path = "/home/public/Cisco_IOS/" + str(tfile)
        tfile = tfile[tfile.find("/")+ 1:]
        #we want everything in the device list except the 1st argument which is the name of this script
        deviceList = sys.argv[1:len(sys.argv) -1]
        #Does this file exist on the device
        if os.path.exists(path):

           deviceList = isValid(deviceList)
           deviceList = versionTest(deviceList, tfile)
           deviceList = deviceFileCheck(deviceList, tfile)
           deviceList = sizeTest(deviceList, tfile, path)
           deviceList = SCPTest(deviceList,tfile, path)
           #I made thereList global. It is used in deviceFileCheck and if the file is already there
           #I appended it to that list and avoided checking the size and scp and skip it right to md5
           deviceList = deviceList + thereList
           deviceList = md5Check(deviceList, tfile,  path)
           deviceList = boot(deviceList, tfile)
           if deviceList == None:
                deviceList = []
           IOSReport(deviceList,errorList)
        else:
          print "\nFile does not exist\n"
          print "Usage:"
          print "python script.py <device 1> ... <device N> <IOS File>"
          print "---------------------------------------------------------"
          print "---------------------------------------------------------"
          sys.exit(1)



if __name__ == "__main__":
    main()