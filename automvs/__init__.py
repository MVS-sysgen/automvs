"""
MVS Automation Python Library
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This library allows the use of MVS/CE, TK5, and TK4- in an automated 
    fashion. This can be used for deploying XMI files, pushing out updates, 
    building software, creating custom MVS deployments.

    Using this library requires a hercules SDL and MVS/CE for MVS/CE and/or
    TK4-/TK5 for those MVS3.8j.
"""

__version__ = '0.0.9'
__author__ = 'Philip Young'
__license__ = "GPL"

# Copyright (c) 2021, Philip Young
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import os
import time
import subprocess
import threading
import queue
import socket
from pathlib import Path
import logging

import http.client
import urllib.parse

TIMEOUT = 1800 # Global time out 30 minutes


def print_maxcc(cc_list):
    '''
    Prints a formatted table of the return codes from the 'check_maxcc' function.

    Args: 
        cc_list (list): a list of dicts
    '''
    # Get the maximum length of each column
    print(" # Completed!\n # Results:\n #")
    max_lengths = {key: max(len(key), max(len(str(item[key])) for item in cc_list)) for key in cc_list[0]}  
    # Print the table headers
    print(" # "+" | ".join(f"{key.ljust(max_lengths[key])}" for key in cc_list[0]))
    # Print a separator line
    print(" # "+"-" * (sum(int(length) for length in max_lengths.values()) + len(max_lengths) + 5 ))
    # Print the table rows
    for row in cc_list:
        exitcode = str(row['exitcode'])
        
        if exitcode == '0000' or exitcode == "*FLUSH*":
            exitcode_msg = ""
        elif str.isdigit(exitcode) and int(exitcode) <= 4:
            exitcode_msg = " <-- Warning"            
        else:
            exitcode_msg = " <-- Failed"
        print(" # "+" | ".join(f"{(exitcode + exitcode_msg).ljust(max_lengths[key])}" if key == 'exitcode' else f"{str(row[key]).ljust(max_lengths[key])}" for key in row))
    
    print(" # "+"-" * (sum(int(length) for length in max_lengths.values()) + len(max_lengths) + 5 ))
    print(" #")

class automation:

    def __new__(self,
                 system_path="mvsce/",
                 system='MVSCE',
                 loglevel=logging.WARNING,
                 config=None,
                 rc=None, 
                 ip='127.0.0.1',
                 punch_port=3505,
                 web_port=8038,
                 timeout=TIMEOUT,
                 username='HERC01',
                 password='CUL8TR'
                ):
    
        if 'MVSCE' in system.upper():

            return(
                mvs(
                 mvsce=system_path,
                 loglevel=loglevel,
                 config=config,
                 rc=rc,
                 timeout=timeout
                )
            )
        elif 'TK5' in system.upper() or 'TK4-' in system.upper():

            return(
                turnkey(
                    ip=ip,
                    system=system,
                    mvs_tk_path=system_path,
                    punch_port=punch_port,
                    web_port=web_port,
                    loglevel=loglevel,
                    timeout=timeout,
                    username=username,
                    password=password
                )
            )
        
        else:
            raise ValueError(f'System must be one of MVSCE, TK5, or TK4-. system={system}')

reply_num = 0

class mvs:
    
    error_check = [
                'open error',
                'Creating crash dump',
                'DISASTROUS ERROR',
                'HHC01023W Waiting for port 3270 to become free for console connections',
                'disabled wait state 00020000 80000005',
                'invalid ipl psw 0000000000000'
              ]
    cwd = os.getcwd()
    quit_herc_event = threading.Event()
    kill_hercules = threading.Event()
    reset_herc_event = threading.Event()
    STDERR_to_logs = threading.Event()
    running_folder = os.getcwd()

    '''
    Mainframe automation class.
    =================================

    This class contains modules to automate MVS/CE. 

    Examples:
        IPL MVS/CE and submit JCL and check the results, attach a device
        and send an operator command::

            >>> from automvs import automation
            >>> cwd = os.getcwd()
            >>> build = automation()
            >>> build.ipl(clpa=False)
            >>> try:
            >>>     print("Submitting {}/jcl/upload.jcl".format(cwd))
            >>>     with open("{}/jcl/upload.jcl".format(cwd),"r") as jcl:
            >>>         build.submit(jcl.read())
            >>>     build.wait_for_string("HASP250 UPLOAD   IS PURGED")
            >>>     build.check_maxcc("UPLOAD")
            >>>     build.send_herc('devinit 170 tape/zdlib1.het')
            >>>     build.wait_for_string("IEF238D SMP4P44 - REPLY DEVICE NAME OR 'CANCEL'.")
            >>>     build.send_reply('170')
            >>>     build.send_oper("$DU")
            >>> finally:
            >>>     build.quit_hercules()


    Args:
        mvsce (str): Path to the MVS/CE folder.
        config (str): OPTIONAL path to a different hercules config file. If
            one is not provided the one included with MVS/CE will be used.
        rc (str): OPTIONAL path to a different hercules rc file. If
            one is not provided the one included with MVS/CE will be used.
        timeout (int): how long, in seconds, to wait for MVS console output
            messages. Default is 30 minutes.
        loglevel (int): Level of logging, based on
            https://docs.python.org/3/library/logging.html#levels.
            Defaults to ``loggin.WARNING``.
    '''
    def __init__(self,
                 mvsce="mvsce/",
                 loglevel=logging.WARNING,
                 config=None,
                 rc=None,
                 timeout=None
                ):

        self.config = config
        self.rc = rc
        self.timeout=timeout
        self.mvsce_location = Path(mvsce)
        self.hercproc = False
        self.stderr_q = queue.Queue()
        self.stdout_q = queue.Queue()


        if not self.config:
            self.config = self.mvsce_location / "conf/local.cnf"
        if not self.rc:
            self.rc = self.mvsce_location / "conf/mvsce.rc"

        # make sure this stuff exists
        if not self.mvsce_location.exists():
            raise Exception("The MVS/CE folder provided does not exist: {}".format(self.mvsce_location))

        if not self.config.exists():
            raise Exception("The MVS/CE config file provided does not exist: {}".format(self.config))
            
        if not self.rc.exists():
            raise Exception("The MVS/CE rc file provided does not exist: {}".format(self.rc))


        # Create the Logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        logger_formatter = logging.Formatter(
            '%(levelname)s :: %(funcName)s :: %(message)s')

        # Log to stderr
        ch = logging.StreamHandler()
        ch.setFormatter(logger_formatter)
        ch.setLevel(loglevel)
        if not self.logger.hasHandlers():
            self.logger.addHandler(ch)

        self.logger.debug("[AUTOMATION: MVS/CE] MVS/CE Location: {}".format(self.mvsce_location))
        self.logger.debug("[AUTOMATION: MVS/CE] MVS/CE config location: {}".format(self.config))
        self.logger.debug("[AUTOMATION: MVS/CE] MVS/CE RC location: {}".format(self.rc))
        self.logger.debug("[AUTOMATION: MVS/CE] Current working directory {}".format(mvs.running_folder))

        self.change_to_mvsce()

    def kill(self):
        self.hercproc.kill()

    def start_threads(self):
        # start a pair of threads to read output from hercules
        self.stdout_thread = threading.Thread(target=self.queue_stdout, args=(self.hercproc.stdout,self.stdout_q))
        self.stderr_thread = threading.Thread(target=self.queue_stderr, args=(self.hercproc.stderr,self.stderr_q))
        self.check_hercules_thread = threading.Thread(target=self.check_hercules, args=[self.hercproc])
        # self.queue_printer_thread = threading.Thread(target=self.queue_printer, args=('prt00e.txt',printer_q))
        self.stdout_thread.daemon = True
        self.stderr_thread.daemon = True
        # self.queue_printer_thread.daemon = True
        self.check_hercules_thread.daemon = True
        self.stdout_thread.start()
        self.stderr_thread.start()
        self.check_hercules_thread.start()
        # self.queue_printer_thread.start()

    def queue_stdout(self, pipe, q):
        ''' queue the stdout in a non blocking way'''
        global reply_num
        while True:

            l = pipe.readline()
            if len(l.strip()) > 0:
                if len(l.strip()) > 3 and l[0:2] == '/*' and l[2:4].isnumeric():
                    reply_num = l[2:4]
                    self.logger.debug("[AUTOMATION: MVS/CE] Reply number set to {}".format(reply_num))
                if  "HHC90020W" not in l and "HHC00007I" not in l and "HHC00107I" not in l and "HHC00100I" not in l:
                    # ignore these messages, they're just noise
                    # HHC90020W 'hthread_setschedparam()' failed at loc=timer.c:193: rc=22: Invalid argument
                    # HHC00007I Previous message from function 'hthread_set_thread_prio' at hthreads.c(1170)
                    self.logger.debug("[HERCLOG] {}".format(l.strip()))
                    q.put(l)
                    for errors in mvs.error_check:
                        if errors in l:
                            self.logger.critical("Quiting! Irrecoverable Hercules error: {}".format(l.strip()))
                            mvs.kill_hercules.set()
            if mvs.reset_herc_event.is_set():
                break

    def queue_stderr(self, pipe, q):
        ''' queue the stderr in a non blocking way'''
        while True:
            l = pipe.readline()
            if len(l.strip()) > 0:
                if mvs.STDERR_to_logs.is_set():
                    self.logger.debug("[DIAG] {}".format(l.strip()))
                if 'MIPS' in l:
                    self.logger.debug("[DIAG] {}".format(l.strip()))
                q.put(l)

                for errors in mvs.error_check:
                    if errors in l:
                        self.logger.debug("Quiting! Irrecoverable Hercules error: {}".format(l.strip()))
                        mvs.kill_hercules.set()
            if mvs.reset_herc_event.is_set():
                break

    def check_hercules(self, hercproc):
        ''' check to make sure hercules is still running '''
        while hercproc.poll() is None:
            if mvs.quit_herc_event.is_set() or mvs.reset_herc_event.is_set():
                self.logger.debug("[AUTOMATION: MVS/CE] Quit Event enabled exiting hercproc monitoring")
                return
            if mvs.kill_hercules.is_set():
                hercproc.kill()
                break
            continue

        self.logger.debug("[ERROR] - Hercules Exited Unexpectedly")
        os._exit(1)

    def check_maxcc(self, jobname, steps_cc={}, printer_file='printers/prt00e.txt',ignore=False):
      '''Checks job and steps results, raises error
          If the step is in steps_cc, check the step vs the cc in the dictionary
          otherwise checks if step is zero

         jobname (str): name of the job to check from the printer file output
         steps_cc (dict): pairs of step names and expected CC. This should be used
            if you expect a specific step to have a return code other than zero.
         printer_file (str): location of the printer file from hercules that
            contains the job output.
         ignore (bool): tells the function to ignore failed steps

         returns: a list of dicts with 'jobname, procname, stepname, exitcode'

      '''
      self.logger.debug("[AUTOMATION: MVS/CE] Checking {} job results".format(jobname))

      found_job = False
      failed_step = False
      job_status = []

      logmsg = '[MAXCC] Jobname: {:<8} Procname: {:<8} Stepname: {:<8} Exit Code: {:<8}'

      with open(printer_file, 'r', errors='ignore') as f:
          for line in f.readlines():
              if 'IEF142I' in line and jobname in line:

                  found_job = True

                  x = line.strip().split()
                  y = x.index('IEF142I')
                  j = x[y:]

                  log = logmsg.format(j[1],'',j[2],j[10])
                  step_status = {
                                    "jobname" : j[1],
                                    "procname": '',
                                    "stepname": j[2],
                                    "exitcode": j[10]
                                }
                  maxcc=j[10]
                  stepname = j[2]

                  if j[3] != "-":
                      log = logmsg.format(j[1],j[2],j[3],j[11])
                      step_status = {
                                        "jobname" : j[1],
                                        "procname": j[2],
                                        "stepname": j[3],
                                        "exitcode": j[11]
                                    }
                      stepname = j[3]
                      maxcc=j[11]

                  self.logger.debug(log)
                  job_status.append(step_status)

                  if stepname in steps_cc:
                      expected_cc = steps_cc[stepname]
                  else:
                      expected_cc = '0000'

                  if maxcc != expected_cc:
                      error = "Step {} Condition Code does not match expected condition code: {} vs {} review prt00e.txt for errors".format(stepname,j[-1],expected_cc)
                      if ignore:
                        self.logger.debug(error)
                      else:
                        self.logger.error(error)
                        
                      failed_step = True

      if not found_job:
          raise ValueError("Job {} not found in printer output {}".format(jobname, printer_file))

      if failed_step and not ignore:
          raise ValueError(error)
        
      return(job_status)


    def reset_hercules(self,clpa=False):
        self.logger.debug('[AUTOMATION: MVS/CE] Restarting hercules')
        self.quit_hercules(msg=False)

        # drain STDERR and STDOUT
        while True:
            try:
                line = self.stdout_q.get(False).strip()
            except queue.Empty:
                break

        while True:
            try:
                line = self.stderr_q.get(False).strip()
            except queue.Empty:
                break

        mvs.reset_herc_event.set()

        try:
            self.hercmd = subprocess.check_output(["which", "hercules"]).strip()
        except:
            raise Exception('hercules not found')

        self.logger.debug("[AUTOMATION: MVS/CE] Launching hercules")

        h = [ "hercules", '--externalgui', '-f',self.config ]

        if not clpa:
            h.append("-r")
            h.append(self.rc)

        self.logger.debug("[AUTOMATION: MVS/CE] Launching hercules with: {}".format(h))

        self.hercproc = subprocess.Popen(h,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True)
        mvs.reset_herc_event.clear()
        mvs.quit_herc_event.clear()
        self.start_threads()

        rc = self.hercproc.poll()
        if rc is not None:
            raise("[AUTOMATION: MVS/CE] Unable to start hercules")
        self.logger.debug("[AUTOMATION: MVS/CE] Hercules launched")
        #self.write_logs()
        self.logger.debug("[AUTOMATION: MVS/CE] Hercules Re-initialization Complete")


    def quit_hercules(self, msg=True):
        if msg:
            self.logger.debug("[AUTOMATION: MVS/CE] Shutting down hercules")
        if not self.hercproc or self.hercproc.poll() is not None:
            self.logger.debug("[AUTOMATION: MVS/CE] Hercules already shutdown")
            return
        mvs.quit_herc_event.set()
        self.send_herc('quit')
        self.wait_for_string('Hercules shutdown complete', stderr=True)
        if msg:
            self.logger.debug('[AUTOMATION: MVS/CE] Hercules has exited')

    def wait_for_job(self, jobname, stderr=False, timeout=False):
        self.wait_for_string("HASP250 {:<8} IS PURGED".format(jobname),stderr=stderr, timeout=timeout)

    def wait_for_string(self, string_to_waitfor, stderr=False, timeout=False):
        '''
           Reads stdout queue waiting for expected response, default is
           to check STDOUT queue, set stderr=True to check stderr queue instead
           default timeout is 30 minutes
        '''
        time_started = time.time()

        if not timeout and self.timeout:
            timeout=self.timeout

        if not timeout:
            timeout = TIMEOUT

        self.logger.debug("[AUTOMATION: MVS/CE] Waiting {} seconds for string to appear in hercules log: {}".format(timeout,string_to_waitfor))

        while True:
            if time.time() > time_started + timeout:
                exception = "Waiting for '{}' timed out after {} seconds".format(string_to_waitfor, timeout)
                print("[AUTOMATION: MVS/CE] {}".format(exception))
                raise Exception(exception)

            try:
                if stderr:
                    line = self.stderr_q.get(False).strip()
                else:
                    line = self.stdout_q.get(False).strip()
                while string_to_waitfor not in line:
                    if stderr:
                        line = self.stderr_q.get(False).strip()
                    else:
                        line = self.stdout_q.get(False).strip()
                    continue
                return

            except queue.Empty:
                #self.logger.debug("Empty Queue")
                continue
            

    def wait_for_strings(self, strings_to_waitfor, stderr=False, timeout=False):
        '''
           Reads stdout queue waiting for expected response, default is
           to check STDOUT queue, set stderr=True to check stderr queue instead
           default timeout is 30 minutes.and

           Unlike wait_for_string() this function takes a list of strings
           and returns when any of the strings in the list are found. 
        '''
        time_started = time.time()

        if not timeout and self.timeout:
            timeout=self.timeout

        if not timeout:
            timeout = TIMEOUT

        self.logger.debug("[AUTOMATION: MVS/CE] Waiting {} seconds for string to appear in hercules log: {}".format(timeout,strings_to_waitfor))

        while True:
            if time.time() > time_started + timeout:
                exception = "Waiting for one of '{}' timed out after {} seconds".format(strings_to_waitfor, timeout)
                print("[AUTOMATION: MVS/CE] {}".format(exception))
                raise Exception(exception)

            try:
                if stderr:
                    line = self.stderr_q.get(False).strip()
                else:
                    line = self.stdout_q.get(False).strip()
                while not any(word in line for word in strings_to_waitfor):
                    if stderr:
                        line = self.stderr_q.get(False).strip()
                    else:
                        line = self.stdout_q.get(False).strip()
                    continue
                for word in strings_to_waitfor:
                    if word in line:
                        break
                return word

            except queue.Empty:
                #self.logger.debug("Empty Queue")
                continue
            

    def ipl(self, step_text='', clpa=False):
        self.logger.debug(step_text)
        self.reset_hercules(clpa=clpa)
        #self.wait_for_string("0:0151 CKD")

        if clpa:
            self.send_herc("ipl 150")
            self.wait_for_string("input for console 0:0009")
            self.send_oper("r 0,clpa")
            # self.wait_for_string('$HASP426 SPECIFY OPTIONS - HASP-II, VERSION JES2 4.1')
            # self.send_oper('r 0,noreq')
                             #IKT005I TCAS IS INITIALIZED
        self.wait_for_string("IKT005I TCAS IS INITIALIZED")

    def shutdown_mvs(self, cust=False):
        self.logger.debug("[AUTOMATION: MVS/CE] Shutting down MVS")
        self.send_oper('$PJES2,ABEND')
        self.wait_for_string("00 $HASP098 ENTER TERMINATION OPTION")
        self.send_oper("r 00,PURGE")
        if cust:
            self.wait_for_string('IEF404I JES2 - ENDED - ')
        else:
            self.wait_for_string('IEF196I IEF285I   VOL SER NOS= SPOOL0.')
        self.send_oper('z eod')
        self.wait_for_string('IEE334I HALT     EOD SUCCESSFUL')
        self.send_oper('quiesce')
        self.wait_for_string("disabled wait state")
        self.send_herc('stop')

    def send_herc(self, command=''):
        ''' Sends hercules commands '''
        self.logger.debug("[AUTOMATION: MVS/CE] Sending Hercules Command: {}".format(command))
        self.hercproc.stdin.write(command+"\n")
        self.hercproc.stdin.flush()

    def send_oper(self, command=''):
        ''' Sends operator/console commands (i.e. prepends /) '''
        self.logger.debug("[AUTOMATION: MVS/CE] Sending Operator command: /{}".format(command))
        self.send_herc("/{}".format(command))

    def send_reply(self, command=''):
        ''' Sends operator/console commands with automated number '''
        self.logger.debug("[AUTOMATION: MVS/CE] Sending reply: /r {},{}".format(reply_num,command))
        self.send_herc("/r {},{}".format(reply_num,command))

    def submit(self,jcl, host='127.0.0.1',port=3505, ebcdic=False):
        '''submits a job (in ASCII) to hercules listener'''
        self.logger.debug("[AUTOMATION: MVS/CE] Submitting JCL host={} port={} EBCDIC={}".format(host,port,ebcdic))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            # Connect to server and send data
            sock.connect((host, port))
            if ebcdic:
              sock.send(jcl)
            else:
              sock.send(jcl.encode())

        finally:
            sock.close()


    def submit_and_check(self, jcl, host='127.0.0.1',port=3505, ebcdic=False, jobname=False):

        if ebcdic and not jobname:
            raise Exception("Auto detection of EBCDIC JCL jobname not support. Missing jobname=")

        if not jobname:
            self.logger.debug("[AUTOMATION: MVS/CE] Getting job name from JCL")
            jobname = jcl.split(" ")[0][2:]
        
        self.logger.debug("[AUTOMATION: MVS/CE] Submitting {}".format(jobname))
        self.submit(jcl, host=host,port=port, ebcdic=ebcdic)
        self.wait_for_job(jobname)
        self.check_maxcc(jobname)
        

    def change_to_mvsce(self):
        self.logger.debug("[AUTOMATION: MVS/CE] Changing to MVS/CE Folder {}".format(self.mvsce_location))
        os.chdir(self.mvsce_location)

    def change_punchcard_output(self,path):
        self.logger.debug("[AUTOMATION: MVS/CE] Changing 3525 Punchcard output location to: '{}'".format(path))
        if not os.path.exists(os.path.dirname(path)): 
            self.logger.debug("[AUTOMATION: MVS/CE] Punchcard folder '{}' does not exist".format(path))
            raise Exception("Punchcard folder '{}' does no exist".format(path))
        self.send_herc(command='detach d')
        self.send_herc(command='attach d 3525 {} ebcdic'.format(path))

class turnkey:

    def __init__(self,
                 system="TK5",
                 mvs_tk_path="mvs-tk5", 
                 ip='127.0.0.1',
                 punch_port=3505,
                 web_port=8038,
                 loglevel=logging.WARNING,timeout=300,
                 username='HERC01',
                 password='CUL8TR'
                ):
        
        self.system = system
        self.mvs_path = mvs_tk_path
        self.ip = ip
        self.timeout = timeout
        if not Path(f"{self.mvs_path}/prt/prt00e.txt").is_file():
            raise Exception(f"could not find TK4/TK5 prt/prt00e.txt file: {self.mvs_path}/prt/prt00e.txt")
        if not Path(f"{self.mvs_path}/log/hardcopy.log").is_file():
            raise Exception(f"could not find TK4/TK5 log/hardcopy.log file: {self.mvs_path}/prt/prt00e.txt")

        self.logfile = f"{self.mvs_path}/log/hardcopy.log"
        self.printer = f"{self.mvs_path}/prt/prt00e.txt"

        self.username = username
        self.password = password

        # Create the Logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        logger_formatter = logging.Formatter(
            '%(levelname)s :: %(funcName)s :: %(message)s')

        # Log to stderr
        ch = logging.StreamHandler()
        ch.setFormatter(logger_formatter)
        ch.setLevel(loglevel)
        if not self.logger.hasHandlers():
            self.logger.addHandler(ch)

        self.punch_port = punch_port
        self.web_port = web_port

        self.logger.debug(f"[AUTOMATION: {self.system}] Using TK Automation with - IP: {self.ip}")
        self.check_ports()

    def submit(self,jcl, ebcdic=False, port=None):
        self.logger.debug(f"[AUTOMATION: {self.system}] Submitting JCL host={self.ip} port={self.punch_port} EBCDIC={ebcdic}")
        #print(jcl)
        self.read_log_lines() #establish baseline
        self.read_prt_lines() #establish baseline
        if not port:
            port = self.punch_port 

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Connect to server and send data
            sock.connect((self.ip, port))
            if ebcdic:
              sock.send(jcl)
            else:
              sock.send(jcl.encode())

        finally:
            sock.close()


    def wait_for_string(self,string_to_waitfor):
        self.logger.debug(f"[AUTOMATION: {self.system}] Waiting for '{string_to_waitfor}' in {self.logfile}")
        time_started = time.time()

        self.logger.debug(f"[AUTOMATION: {self.system}] Waiting {self.timeout} seconds for string to appear in hercules log: {string_to_waitfor}")

        while True:
            if time.time() > time_started + self.timeout:
                exception = f"Waiting for '{string_to_waitfor}' timed out after {self.timeout} seconds"
                print("[ERR] {}".format(exception))
                raise Exception(exception)

            new_lines = self.read_log_lines()
            for line in new_lines:
                if string_to_waitfor in line:
                    return



    def wait_for_strings(self,strings_to_waitfor):
        '''
        Unlike string to wait for this function 
        '''
        self.logger.debug(f"[AUTOMATION: {self.system}] Waiting for any of these strings '{strings_to_waitfor}' in {self.logfile}")
        time_started = time.time()

        self.logger.debug(f"[AUTOMATION: {self.system}] Waiting {self.timeout} seconds for strings to appear in hercules log: {strings_to_waitfor}")

        while True:
            if time.time() > time_started + self.timeout:
                exception = f"Waiting for any of the strings timed out after {self.timeout} seconds"
                print("[ERR] {}".format(exception))
                raise Exception(exception)

            new_lines = self.read_log_lines()
            for line in new_lines:
                if any(word in line for word in strings_to_waitfor):
                    return

    def wait_for_job(self, jobname):
        self.wait_for_string("HASP250 {:<8} IS PURGED".format(jobname))

    def change_punchcard_output(self,path):
        self.logger.debug(f"[AUTOMATION: {self.system}] Changing 3525 Punchcard output location to: '{path}'")
        if not os.path.exists(os.path.dirname(path)): 
            self.logger.debug(f"[AUTOMATION: {self.system}] Punchcard folder '{path}' does not exist")
            raise Exception("Punchcard folder '{}' does not exist".format(path))
        self.send_herc(command='detach d')
        self.send_herc(command='attach d 3525 {} ebcdic'.format(path))

    def read_log_lines(self):
        #self.logger.debug(f"reading {self.logfile}")
        with open(self.logfile, "r") as file:
            # Check if the last_size attribute exists in the instance
            if not hasattr(self, 'log_last_size'):
                # If not, initialize it to 0
                self.log_last_size = 0
            
            # Move the cursor to the last known position
            file.seek(self.log_last_size)
            
            # Read new lines
            new_lines = file.readlines()

            for line in new_lines:
                self.logger.debug(f"[LOG] {line.strip()}")
            
            # Update the last known file size
            self.log_last_size = file.tell()
            #self.logger.debug(f"returning {len(new_lines)} lines")
            return new_lines

    
    def read_prt_lines(self):
        #self.logger.debug(f"reading {self.logfile}")
        with open(self.printer, "r",errors='ignore') as file:
            # Check if the last_size attribute exists in the instance
            if not hasattr(self, 'prt_last_size'):
                # If not, initialize it to 0
                self.prt_last_size = 0
            
            # Move the cursor to the last known position
            file.seek(self.prt_last_size)
            
            # Read new lines
            new_lines = file.readlines()

            # if self.prt_last_size > 0 :
            #     for line in new_lines:
            #         self.logger.debug(f"[PRT] {line.strip()}")
            
            # Update the last known file size
            self.prt_last_size = file.tell()
            #self.logger.debug(f"returning {len(new_lines)} lines")
            return new_lines

    def check_maxcc(self, jobname, steps_cc={},ignore=False):
        self.logger.debug(f"[AUTOMATION: {self.system}] Checking {jobname} job results")

        found_job = False
        failed_step = False
        job_status = []
        log = None

        logmsg = '[MAXCC] Jobname: {:<8} Procname: {:<8} Stepname: {:<8} Progname: {:<8} Exit Code: {:<8}'
        for line in self.read_prt_lines():
            #print(line.strip())
            if 'IEF403I' in line and f' {jobname} ' in line:
                found_job = True
                continue
            

            if ('IEF404I' in line or 'IEF453I' in line) and jobname in line:
                break

            if found_job and f' {jobname} ' in line and ' ABEND ' not in line:

                x = line.strip().split()
                #y = x.index('IEF142I')
                j = x[3:]
                #print(j)
                if len(j) == 5:
                    log = logmsg.format(j[0],'',j[1],j[2],j[4])
                    step_status = {
                                    "jobname:" : j[0],
                                    "procname": '',
                                    "stepname": j[1],
                                    "progname": j[2],
                                    "exitcode": j[4]
                                }
                    maxcc=j[4]
                    stepname = j[1]

                elif len(j) == 6:
                    log = logmsg.format(j[0],j[2],j[1],j[3],j[5])
                    step_status = {
                                    "jobname:" : j[0],
                                    "procname": j[2],
                                    "stepname": j[1],
                                    "progname": j[3],
                                    "exitcode": j[5]
                                }
                    stepname = j[3]
                    maxcc=j[5]

                elif len(j) == 4:
                    log = logmsg.format(j[0],'',j[1],j[2],j[3])
                    step_status = {
                                    "jobname:" : j[0],
                                    "procname": '',
                                    "stepname": j[1],
                                    "progname": j[2],
                                    "exitcode": j[3]
                                }
                    maxcc=j[3]
                    stepname = j[1]

                self.logger.debug(log)
                job_status.append(step_status)

                if stepname in steps_cc:
                    expected_cc = steps_cc[stepname]
                else:
                    expected_cc = '0000'

                if maxcc != expected_cc:
                    error = "[MAXCC] Step {} Condition Code does not match expected condition code: {} vs {} review prt00e.txt for errors".format(stepname,j[-1],expected_cc)
                    if ignore:
                        self.logger.debug(error)
                    else:
                        self.logger.error(error)
                    failed_step = True

        if not found_job:
            raise ValueError("Job {} not found in printer output {}".format(jobname, self.printer))

        if failed_step and not ignore:
            self.logger.error(f"Job Failed with maxcc: {maxcc}")
            print_maxcc(job_status)
            raise ValueError(error)
            
        return(job_status)

    def hercules_web_command(self,command=''):
        
        cmd = f"/cgi-bin/tasks/syslog?command=" + urllib.parse.quote(command)
        conn = http.client.HTTPConnection(self.ip, self.web_port)
        conn.request("GET", cmd)
        response = conn.getresponse()
        conn.close()

    def send_herc(self, command=''):
        ''' Sends hercules commands '''
        self.logger.debug(f"[AUTOMATION: {self.system}] Sending Hercules Command: {command}")
        self.hercules_web_command(command)

    def send_oper(self, command=''):
        ''' Sends operator/console commands (i.e. prepends /) '''
        self.logger.debug(f"[AUTOMATION: {self.system}] Sending Operator command: /{command}")
        self.send_herc(f"/{command}")
    
    def check_ports(self):
        self.logger.debug(f"[AUTOMATION: {self.system}] Checking if {self.system} ports are available")
        self.check_port(self.ip,self.punch_port)
        self.check_port(self.ip,self.web_port)

    def check_port(self, ip, port):
        self.logger.debug(f"[AUTOMATION: {self.system}] Checking {ip}:{port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)  # Set a timeout for the connection attempt

        try:
            # Attempt to connect to the IP address and port
            result = sock.connect_ex((ip, port))
            if result == 0:
                self.logger.debug(f"[AUTOMATION: {self.system}] Port {port} is open")
            else:
                self.logger.debug(f"[AUTOMATION: {self.system}] Port {port} is closed")
                raise Exception(f"Port {port} is not available, is TK5 running?")
        except Exception as e:
            raise Exception(f"Error checking port {port}: {e}")
        finally:
            # Close the socket
            sock.close()

    def jobcard(self, jobname, title, jclass='A', msgclass='A'):
        '''
        This function generates the jobcard needed to submit the jobs
        '''

        jobcard = ( 
                  "//{jobname} JOB (BREXX),'{title}'," +
                  "//       CLASS={jclass},MSGCLASS={msgclass}, " +
                  "//       REGION=8M,MSGLEVEL=(1,1),USER={user},PASSWORD={password} " +
                  "//********************************************************************\n"
                  )

        return jobcard.format(
            jobname=jobname.upper(),
            title=title,
            jclass=jclass,
            msgclass=msgclass,
            user=self.username.upper(),
            password=self.password.upper()
            )

    def test(self,times=5):
        t = ''
        for i in range(1,times):
            t += f"//TEST{i} EXEC PGM=IEFBR14\n"

        proc = "//TSTPROC      PROC\n//TESTPROC  EXEC  PGM=IEFBR14\n// PEND\n"
        p = ''
        for i in range(1,times):
            p += f"//TST{i}     EXEC TSTPROC\n"

        self.submit(self.jobcard('test','test job')+t+proc+p)
        self.wait_for_string("$HASP250 TEST     IS PURGED")
        results = self.check_maxcc('TEST')
        self.logger.debug("TEST Completed Succesfully")
        print_maxcc(results)
        self.send_herc('/$da')
        self.send_oper('$da')