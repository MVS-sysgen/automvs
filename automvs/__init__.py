"""
MVS Automation Python Library
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This library allows the use of MVS/CE in an automated fashion. This can
    be used for deploying XMI files, pushing out updates, building software,
    creating custom MVS deployments.

    Using this library requires a recent version of hercules SDL and MVS/CE.
"""

__version__ = '0.0.7-3'
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

cwd = os.getcwd()

TIMEOUT = 1800 # Global time out 30 minutes

error_check = [
                'open error',
                'Creating crash dump',
                'DISASTROUS ERROR',
                'HHC01023W Waiting for port 3270 to become free for console connections',
                'disabled wait state 00020000 80000005',
                'invalid ipl psw 0000000000000'
              ]

reply_num = 0

quit_herc_event = threading.Event()
kill_hercules = threading.Event()
reset_herc_event = threading.Event()
STDERR_to_logs = threading.Event()
running_folder = os.getcwd()

class automation:
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

        self.logger.debug("MVS/CE Location: {}".format(self.mvsce_location))
        self.logger.debug("MVS/CE config location: {}".format(self.config))
        self.logger.debug("MVS/CE RC location: {}".format(self.rc))
        self.logger.debug("[AUTOMATION] Current working directory {}".format(cwd))

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
                    self.logger.debug("[AUTOMATION] Reply number set to {}".format(reply_num))
                if  "HHC90020W" not in l and "HHC00007I" not in l and "HHC00107I" not in l and "HHC00100I" not in l:
                    # ignore these messages, they're just noise
                    # HHC90020W 'hthread_setschedparam()' failed at loc=timer.c:193: rc=22: Invalid argument
                    # HHC00007I Previous message from function 'hthread_set_thread_prio' at hthreads.c(1170)
                    self.logger.debug("[HERCLOG] {}".format(l.strip()))
                    q.put(l)
                    for errors in error_check:
                        if errors in l:
                            self.logger.critical("Quiting! Irrecoverable Hercules error: {}".format(l.strip()))
                            kill_hercules.set()
            if reset_herc_event.is_set():
                break

    def queue_stderr(self, pipe, q):
        ''' queue the stderr in a non blocking way'''
        while True:
            l = pipe.readline()
            if len(l.strip()) > 0:
                if STDERR_to_logs.is_set():
                    self.logger.debug("[DIAG] {}".format(l.strip()))
                if 'MIPS' in l:
                    self.logger.debug("[DIAG] {}".format(l.strip()))
                q.put(l)

                for errors in error_check:
                    if errors in l:
                        self.logger.debug("Quiting! Irrecoverable Hercules error: {}".format(l.strip()))
                        kill_hercules.set()
            if reset_herc_event.is_set():
                break

    def check_hercules(self, hercproc):
        ''' check to make sure hercules is still running '''
        while hercproc.poll() is None:
            if quit_herc_event.is_set() or reset_herc_event.is_set():
                self.logger.debug("[AUTOMATION] Quit Event enabled exiting hercproc monitoring")
                return
            if kill_hercules.is_set():
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
      self.logger.debug("[AUTOMATION] Checking {} job results".format(jobname))

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
        self.logger.debug('[AUTOMATION] Restarting hercules')
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

        reset_herc_event.set()

        try:
            self.hercmd = subprocess.check_output(["which", "hercules"]).strip()
        except:
            raise Exception('hercules not found')

        self.logger.debug("[AUTOMATION] Launching hercules")

        h = [ "hercules", '--externalgui', '-f',self.config ]

        if not clpa:
            h.append("-r")
            h.append(self.rc)

        self.logger.debug("[AUTOMATION] Launching hercules with: {}".format(h))

        self.hercproc = subprocess.Popen(h,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True)
        reset_herc_event.clear()
        quit_herc_event.clear()
        self.start_threads()

        rc = self.hercproc.poll()
        if rc is not None:
            raise("[AUTOMATION] Unable to start hercules")
        self.logger.debug("[AUTOMATION] Hercules launched")
        #self.write_logs()
        self.logger.debug("[AUTOMATION] Hercules Re-initialization Complete")


    def quit_hercules(self, msg=True):
        if msg:
            self.logger.debug("[AUTOMATION] Shutting down hercules")
        if not self.hercproc or self.hercproc.poll() is not None:
            self.logger.debug("[AUTOMATION] Hercules already shutdown")
            return
        quit_herc_event.set()
        self.send_herc('quit')
        self.wait_for_string('Hercules shutdown complete', stderr=True)
        if msg:
            self.logger.debug('[AUTOMATION] Hercules has exited')

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

        self.logger.debug("[AUTOMATION] Waiting {} seconds for string to appear in hercules log: {}".format(timeout,string_to_waitfor))

        while True:
            if time.time() > time_started + timeout:
                exception = "Waiting for '{}' timed out after {} seconds".format(string_to_waitfor, timeout)
                print("[AUTOMATION] {}".format(exception))
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
        self.logger.debug("Shutting down MVS")
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
        self.logger.debug("[AUTOMATION] Sending Hercules Command: {}".format(command))
        self.hercproc.stdin.write(command+"\n")
        self.hercproc.stdin.flush()

    def send_oper(self, command=''):
        ''' Sends operator/console commands (i.e. prepends /) '''
        self.logger.debug("[AUTOMATION] Sending Operator command: /{}".format(command))
        self.send_herc("/{}".format(command))

    def send_reply(self, command=''):
        ''' Sends operator/console commands with automated number '''
        self.logger.debug("[AUTOMATION] Sending reply: /r {},{}".format(reply_num,command))
        self.send_herc("/r {},{}".format(reply_num,command))

    def submit(self,jcl, host='127.0.0.1',port=3505, ebcdic=False):
        '''submits a job (in ASCII) to hercules listener'''
        self.logger.debug("[AUTOMATION] Submitting JCL host={} port={} EBCDIC={}".format(host,port,ebcdic))
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
            self.logger.debug("[AUTOMATION] Getting job name from JCL")
            jobname = jcl.split(" ")[0][2:]
        
        self.logger.debug("[AUTOMATION] Submitting {}".format(jobname))
        self.submit(jcl, host=host,port=port, ebcdic=ebcdic)
        self.wait_for_job(jobname)
        self.check_maxcc(jobname)
        

    def change_to_mvsce(self):
        self.logger.debug("[AUTOMATION] Changing to MVS/CE Folder {}".format(self.mvsce_location))
        os.chdir(self.mvsce_location)

    def change_punchcard_output(self,path):
        self.logger.debug("[AUTOMATION] Changing 3525 Punchcard output location to: '{}'".format(path))
        if not os.path.exists(os.path.dirname(path)): 
            self.logger.debug("[AUTOMATION] Punchcard folder '{}' does not exist".format(path))
            raise Exception("Punchcard folder '{}' does no exist".format(path))
        self.send_herc(command='detach d')
        self.send_herc(command='attach d 3525 {} ebcdic'.format(path))
