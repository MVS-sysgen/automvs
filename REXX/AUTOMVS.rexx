/* This REXX Script is used by the AUTOMVS Python library to automate */
/* Checking the status of jobs, obatining the results of each step,   */
/* returning a base64 encoded version of any file and returning the   */
/* job log                                                            */

VERSION = '1.0.0'

parse arg arguments
call argparse arguments

call log 'Running as user' userid()

  /*         */
 /* Globals */
/*         */

attempts = 0               /* Logon Attempts        */
logon = 0                 /* Is someone logged on  */
connected = 0            /* Is someone connected? */
max_file_size = 1500000 /* We run out of memory when files are too big */

  /*                                */
 /* Call TCPSF to start the server */
/*                                */

call TCPSF port,timeout,'AUTOMVS','ERROR'
exit 0
/* *********************************************************************
 * Here follow the Events, called by TCPSF as call-back
 * *********************************************************************
 */
/* ---------------------------------------------------------------------
 * Receive Data from Client, arg(1) original data, arg(2) data
 *         arg(1) original data,
 *         arg(2) ebcdic data translated from ascii
 * ---------------------------------------------------------------------
 */
TCPData:
  parse arg #fd,omsg,emsg
  /* Remove the newline character if present */
  if right(emsg, 1) = '25'x then emsg = substr(emsg, 1, length(emsg)-1)
  call verbose 'TCPData: Received:' emsg

  /* command = the first argument recieved */
  /* values = anything following the command */
  parse var emsg command values

  command = UPPER(command)

  select
    when command = '/LOGON' then do

      /* We don't want people brute forcing accounts */
      /* Allow 3 attempts then kick them off */

      if attempts > 2 then do
        call log 'Too many attempts from' #fd
        call send #fd 'Too many failed attempts. Goodbye'
        return 4
      end

      parse var values username password
      attempts = attempts + 1
      call check_user #fd username password
    end

    when command = '/QUIT' then do
      call send #fd 'Goodbye'
      call log 'received quit' #fd
      return 4 /* close  connection */
    end

    when command = '/SHUTDOWN' then do
      if check_logon(#fd '/SHUTDOWN') then do
        call log 'received shutdown' #fd
        return 8 /* shutdown the server */
      end
    end

    when command = '/JOB' then do
      parse var values jobname sendlog .
      call verbose 'TCPData: Checking job' values
      if check_logon(#fd '/JOB') then do
        parse var values jobname job_args

        do while job_args \= ''
          parse var job_args _carg job_args
          
          if pos('DEBUG', upper(_carg)) > 0 then do
            call verbose 'TCPData:' #fd '/JOB - Detailed log requested'
            job_debug = 1
          end

          if pos('TIMEOUT=',upper(_carg)) > 0 then do
            call verbose 'Setting' _carg
            _oldtimeout = timeout
            parse var _carg . '=' timeout
          end
        end

        if length(jobname) > 0 then do
          call check_job #fd jobname job_debug
          timeout = _oldtimeout
        end
        else do
          call send #fd '/JOB requires a jobname'
        end
      end
    end

    when command = '/WAITFOR' then do
      /* wait for specific strings in the log */
      if check_logon(#fd '/WAITFOR') then do
        call wait_for_string #fd values
      end
    end

    when command = '/PURGE' then do
      /* wait for specific strings in the log */
      if check_logon(#fd '/PURGE') then do
        parse var values purge_jobnum purge_jobname
        if datatype(purge_jobnum)='NUM' & purge_jobnum>0 then do
          call verbose 'Purging JOB' purge_jobname ' #'purge_jobnum
          call send #fd '--- Purging JOB' purge_jobname ' #'purge_jobnum
          call CONSOLE('$P J'purge_jobnum)
          call send #fd '--- DONE'
        end
        else do
          call send #fd 'Error: Job number required for /PURGE:' purge_jobnum
        end
      end
    end

    when command = '/HERCULES' then do
      /* wait for specific strings in the log */
      if check_logon(#fd '/HERCULES') then do
        call verbose #fd 'Issuing Hercules command:' values
        call outtrap('herc_console.')
        CALL PRIVILEGE('ON')
        ADDRESS COMMAND 'CP' values
        CALL PRIVILEGE('OFF')
        call outtrap('off')
        call send #fd '--- Log for oper command:' values
        do i=1 to herc_console.0
          call send #fd herc_console.i
        end 
        call send #fd '--- DONE'
      end
    end

    when command = '/OPER' then do
      /* wait for specific strings in the log */
      if check_logon(#fd '/OPER') then do
        call verbose #fd 'Issuing Oper command:' values
        /* We're using undocumented 'STEM' argument */
        /* cause arrays are unstable */
        call rxconsol(values,,'STEM')
        call send #fd '--- Log for oper command:' values '('console.0')'
        do i=1 to console.0
          call send #fd console.i
        end
        call send #fd '--- DONE'
      end
    end

    when command = '/FILE' then do
      if check_logon(#fd '/FILE') then do
        call verbose 'TCPData:' #fd '/FILE - User' username 'access granted'
        parse var values dsn .
        BIN_FILE = ''
        call verbose 'TCPData: Fetching requested dataset' dsn
        dsn_hndl = OPEN("'"dsn"'",'RB,VMODE=2,UMODE=0','DSN')

        IF dsn_hndl = -1 THEN DO
          rmsg = "Error: opening file '"dsn"'"
          call log rmsg
          call send #fd rmsg
        END
        else if check_file_size(dsn_hndl) then do 
          rmsg = "Error: '"dsn"' size "_size" is larger than the",
                 "maximum allowed file size of "max_file_size
          call log rmsg
          call send #fd rmsg
          R = CLOSE(dsn_hndl)
        end
        else do
          CALL seek dsn_hndl,0,"TOF" 
          BIN_FILE = BIN_FILE''READ(dsn_hndl,'F') /* Read the whole file */          
          call log "Sending '"dsn"' Size: " length(BIN_FILE)
          call send #fd '--- Sending BASE64 Encoded File'
          call send #fd BASE64ENC(BIN_FILE)
          call send #fd '--- DONE'
          R = CLOSE(dsn_hndl)
        end
      end
    end

    otherwise do
      call verbose 'TCPData:' #fd "Unrecognized Command: '"command"'"
      call send #fd "Unrecognized Command: '"command"'"
      call check_logon #fd command
    end
  end

return 0     /* proceed normally  */
return 4     /* close  connection */
return 8     /* stop Server       */

send:
    parse arg #fd msg
    call verbose 'send: ('#fd') Sending ' length(msg) 'bytes'
    if length(msg) < 250 then do
      if right(msg, 1) \= '25'x then msg = msg'25'x
      SendLength=TCPSEND(#fd, e2a(msg))

      if SendLength = -1 then
        call log 'Socket Error sending to' #fd sendlength
      if SendLength = -2 then
        call log 'Client not receiving data' #fd sendlength
    end
    else do /* Larger files needs to be broken up */
   
        do y = 1 to length(msg) by 80
          bytes = substr(msg, y, 80)
          SendLength=TCPSEND(#fd, e2a(bytes'25'x))

          if SendLength = -1 then do
            call log 'Socket Error sending to' #fd sendlength
            leave
          end

          if SendLength = -2 then do
            call log 'Client not receiving data' #fd sendlength
            leave
          end

        end
    end
    return
/* ---------------------------------------------------------------------
 * Connect to socket was requested
 *         arg(1): socket number
 * This is just an informal call. All TCP related activites are done.
 * you can for example maintain a list of users, etc.
 * ---------------------------------------------------------------------
 */
TCPconnect:
    parse arg #fd .
    call verbose 'TCPconnect: Connect Request for ' #fd
    if connected = 1 then do
      call log 'Multiple clients are not supported'
      call send #fd 'Only one client allowed per sever. Goodbye'
      return 4
    end
    call send #fd "Welcome to AUTOMVS REXX Server: v"version
    call send #fd 'Please /LOGON to continue'
    connected = 1

return 0     /* proceed normally  */
return 4     /* reject connection */
return 8     /* stop Server       */
/* ---------------------------------------------------------------------
 * Time out occurred, here you can perform non TCP related work.
 * ---------------------------------------------------------------------
 */
TCPtimeout:
return 0     /* proceed normally  */
return 8     /* stop Server       */
/* ---------------------------------------------------------------------
 * Close one client socket
 *         arg(1): socket number
 * This is just an informal call. The close has already be peformed
 * you can for example update your list of users, etc.
 * ---------------------------------------------------------------------
 */
TCPcloseS:
  call log 'User' username 'logged off'
  call log 'Closed Connection 'arg(1)
  attempts = 0
  connected = 0
  logon = 0
return 0     /* proceed normally  */
return 8     /* stop Server       */
/* ---------------------------------------------------------------------
 * Shut Down, application cleanup. TCP cleanup is done internally
 * This is just an informal call. The TCP shutdown has been peformed
 * you can do a final cleanup, etc.
 * ---------------------------------------------------------------------
 */
TCPshutDown: 
  call log 'Shutting Down AUTOMVS'
return


argparse:
    parse arg args
    call verbose 'argparse:' args
    port = 9856 /* Default port */
    timeout = 60 /* Default timeout */
    debug = 0
    call log 'Arguments:' args
    do while (LENGTH(args) > 0)
        parse var args argument args
        if pos('-TIMEOUT',UPPER(argument))>0 then do
            parse var args value args
            call log 'TIMEOUT set to' value
            timeout = value
        end
        if pos('-PORT',UPPER(argument))>0 then do
            parse var args value args
            call log 'PORT set to' value
            port = value
        end
        if pos('DEBUG',UPPER(argument)) > 0 then do
            debug = 1
        end
    end
    call log 'Port set to:' port 'Timeout set to:' timeout
    if debug then call log 'Debug log enabled'
    return

check_job:
  parse arg #fd jobname full_log .
  call verbose 'check_job: jobname' jobname 'debug' full_log
  jobname = upper(jobname)

  call verbose 'check_job: Searching the MTT for the job read message'
  /* The below can sometimes cause an undending loop */
  /* result = MTTX('R',JARRAY,100,'$HASP100 '||JOBNAME) */
  jobnum = get_jobnum(jobname)

  if jobnum = 0 then do
    call verbose 'check_job: Error: Unable to find' jobname 'in MTT' jobnum
    call send #fd 'Error: Unable to find' jobname 'in MTT' jobnum
    return
  end

  if jobnum = -1 then do
    call verbose 'check_job: Error: Unable to read master trace table'
    call send #fd 'Error: Unable to read master trace table'
    return
  end

  call verbose 'check_job: Jobname' jobname 'assigned job number' jobnum
  HASP395 = 'JOB'RIGHT(JOBNUM,5) ' $HASP395' LEFT(JOBNAME,8) 'ENDED'
  HASP250 = 'JOB'RIGHT(JOBNUM,5) ' $HASP250' LEFT(JOBNAME,8) 'IS PURGED'
  
  DONE = 0
  T  = time('s')
  
  call verbose 'check_job: Waiting' timeout 'seconds for' jobname '#'jobnum

  do while done = 0

    done = mtt_search(hasp395) /* JOBNAME  ENDED */

    if done = 0 then do
      done = mtt_search(hasp250) /* JOBNAME  IS PURGED */
    end

    call verbose 'seconds:' (time('s') - t) 'timeout' timeout 'found' done

    if time('s') - t >= timeout then do
      call verbose 'check_job: error: job' jobname '('jobnum') ended not found'
      call send #fd 'Error: job' jobname '('jobnum') ENDED/PURGED not found'
      return
    end
    call wait(1000) /* Don't thrash the CPU wait a bit */

  end

  call verbose 'check_job: Done waiting for' jobname '#'jobnum

  call verbose 'check_job: Getting all log entries for JOB #'jobnum
  
  IEFACTRT = 0
  cc_stem_count = 1
  mtt_rc = mtt('REFRESH')
  call verbose 'check_job: Processing' _line.0 'MTT entries rx' mtt_rc

  if mtt_rc = -1 then do
    call verbose 'check_job: Error: Unable to read master trace table'
    call send #fd 'Error: Unable to read master trace table'
    return
  end

  call verbose 'check_job: Processing' _line.0 'MTT entries'

  if full_log = 1 then call send #fd '--- *JOBLOG* Full Log'

  do i=1 to _line.0

    if pos('JOB'RIGHT(JOBNUM,5),_line.i) > 0 then do
      if full_log = 1 then do
        call send #fd '*JOBLOG*' _line.i
      end

      if pos('IEFACTRT',_line.i) > 0 then do
        call verbose 'check_job: Found IEFACTRT'
        iefactrt = 1
        iterate
      end
    end

    if pos('IEF404I',_line.i) > 0 then do
      call verbose 'check_job: Found IEF404I'
      iefactrt = 0
    end

    if iefactrt = 1 then do
      call verbose 'check_job: parsing:' _line.i

      parse var _line.i _jtype =5 _jtime =14 . =18 num =24,
                name =34 step =44 proc =54 prog retcode

      if strip(_jtype) \= '0004' then iterate /* skip error messages */
      if (strip(num) \= jobnum) then iterate
      if (strip(name) \= jobname) then iterate

      parse var retcode . rcnum /* RC= xxxx or AB xxxx, vs *FLUSH* */
      if length(rcnum) = 0 then rcnum = retcode

      rcnum = retcode
      if pos('RC=',retcode) > 0 then parse var retcode . rcnum
      if pos('AB',retcode) > 0 then parse var retcode . rcnum



      maxcc.cc_stem_count = num','name','step','proc','prog','rcnum
      call verbose 'check_job: parsed line:' maxcc.cc_stem_count
      cc_stem_count = cc_stem_count + 1
    end
  end


  maxcc.0 = cc_stem_count - 1
  call verbose "Done processing MTT entries"

  if full_log = 1 then call send #fd '--- *JOBLOG* Done'

  call verbose "Sending" maxcc.0 'result(s)'

  call send #fd '--- Job Results ('maxcc.0')'

  do i = 1 to maxcc.0
    call send #fd maxcc.i
    call verbose 'Results line' i':' maxcc.i
  end
  call send #fd '--- DONE'
  return

wait_for_string:
  parse arg #fd srch_for
  call verbose 'wait_for_string: Waiting for' srch_for 'in MTT'
  call send #fd '--- Waiting' timeout 'seconds for' srch_for
  
  DONE = 0
  T  = time('s')
  
  do while done = 0

    done = mtt_search(srch_for) /* JOBNAME  ENDED */

    call verbose 'seconds:' (time('s') - t) 'timeout' timeout 'found' done

    if time('s') - t >= timeout then do
      call verbose 'wait_for_string: string: "'srch_for'" not found'
      call send #fd 'Error: string not found in MTT:' srch_for
      return
    end
    call wait(1000) /* Don't thrash the CPU wait a bit */

  end
  call send #fd '--- DONE'
  return

check_user:
  parse arg #fd username password
  call verbose 'Checking' #fd 'username' username 'password ********'


  call verbose 'check_user: Reading SYS1.SECURE.CNTL(USERS)'
  dsn_hndl = OPEN("'SYS1.SECURE.CNTL(USERS)'",'RT','DSN')
  IF dsn_hndl = -1 THEN DO
    call log '*** Unable to open RAKF database'
    call log 'AUTOMVS must run with read access to the RAKF database'
    total_users = 1
  END
  else do
    total_users = 1
    DO UNTIL EOF(dsn_hndl)=1
      rakf_line = READ(dsn_hndl)
      RAKFDB.total_users = rakf_line
      total_users = total_users + 1
    END
    R = CLOSE(dsn_hndl)
  end

  RAKFDB.0 = total_users - 1

  DO I=1 TO RAKFDB.0
    PARSE VAR RAKFDB.I CUR_USER GROUP CUR_PASS .
    if left(cur_user,1) = '*' then iterate /* ignore comments */
    /* call verbose 'Checking' username '=' CUR_USER  */

    if left(cur_pass,1) = '*' then do
      cur_pass = right(cur_pass,length(cur_pass)-1)
    end

    IF CUR_USER = UPPER(username) &,
       HASHVALUE(CUR_PASS) = UPPER(PASSWORD) then do
      call verbose 'check_user: User and password for' username 'found'
      if GROUP = 'RAKFADM' then do
        attempts = 0
        logon = 1
        call send #fd 'LOGON OK'
        call log '('#fd') RAKFADM User' username 'logged on'
        return
      end
    END
  END

  if logon = 0 then do
    call log '('#fd') Access Denied:' username 
    call send #fd 'Logon Failed: Username/password invalid or user',
                  'not in appropriate group'
  end
  return

mtt_search:
  /* Search the master trace table */
  parse arg _srch
  call verbose 'mtt_search: Checking for' _srch

  call verbose 'mtt_search: opening MTT'
  a = mtt('REFRESH')
  call verbose 'mtt_search: MTT total entries:' a
  if a = -1 then return -1

  do i=_line.0 to 1 by -1
    if pos(_srch,_line.i)	>	0	then	do
    call verbose 'mtt_search: Job' _srch 'found:' _line.i
    return 1
    end
  end

  return 0


get_jobnum:
  parse arg _jname
  call verbose 'get_jobnum: Checking for' _jname

  call verbose 'get_jobnum: opening MTT'
  a = mtt('REFRESH')
  call verbose 'get_jobnum: MTT total entries:' a
  if a = -1 then return -1

  _jobnum = 0

  do i=_line.0 to 1 by -1
    call verbose 'get_jobnum: ('i')' _line.i
    if pos('$HASP100 '_jname,_line.i)	>	0	then	do
      call verbose 'get_jobnum: Job' _jname 'found:' _line.i
      parse var _line.i  . . . _jobnum .
      leave
    end
  end

  return _jobnum

check_file_size:
  parse arg file_handler
  _size = SEEK(file_handler,0,"EOF")
  if _size > max_file_size then return 1
  return 0


failed_logon:
    parse var #fd command
    call verbose 'failed_logon:' #fd command '- access denied'
    call verbose 'failed_logon:' #fd command '- access denied'
    call send #fd 'Access Denied'
    call send #fd 'Please /LOGON to continue'
    return

check_logon:
  parse var #fd command
  call verbose "check_logon: "#fd" Checking if client is logged in"
  if logon = 0 then do
    call failed_logon #fd command
    return 0
  end
  call verbose 'check_logon: ('#fd')' command '-' username 'access granted'
  return 1

log:
  parse arg txt
  say time('l') txt
  call wto "AUTOMVS" time('l') txt
  return

verbose:
  parse arg str
  if debug = 1 then say time('l') str
  return

/* ---------------------------------------------------------------------
 * To avoid using RXLIB we include various RXLIB members here here 
 * ---------------------------------------------------------------------
 */

/* ---------------------------------------------------------------------
 * TCP Server Facility
 *     This is the generic TCP Server module which handles all events
 *     The user specific handling of the events is performed
 *     by a call-back to the calling REXX
 *         connect
 *         receive
 *         close
 *         stop
 * ---------------------------------------------------------------------
 */
tcpsf:
  parse arg port,timeout,svrname,MSLV
  if timeout=''  then timeout=60
  if svrname='' then svrname='DUMMY'
  if mslv='' then mslv=0
  else if mslv='NOMSG' then mslv=12
  else if mslv='ERROR' then mslv=8
  else if mslv='WARN'  then mslv=4
  else if mslv='INFO'  then mslv=0
  tcpmsg.0='..BASIC'
  tcpmsg.1='  INFO '
  tcpmsg.4='**WARN '
  tcpmsg.8='++ERROR'
  maxrc=0
  tcpstarted=0
  if datatype(port)<>'NUM' then do
     call _#SVRMSG 8,"Port Number missing or invalid "port
     return 8
  end
  call tcpinit()
  call _#SVRMSG 0,'TCP Server start at Port: 'port
  call _#SVRMSG 1,'TCP Time out set to     : 'timeout' seconds'
  rc=tcpserve(port)
  if rc <> 0 then do
     tcpstarted=1
     call _#SVRMSG 8,"TCP Server start ended with rc: "rc
     return 8
  end
  call _#SVRMSG 1,'TCP Server has been started'
  if nomsg=0 then call wto 'TCP Server has been started, port 'port
  call eventhandler
  call _#SVRMSG 1,"TCP Server will be closed"
  if tcpStarted=1 then call tcpTerm()
  call _#SVRMSG 1,"TCP Server has been closed"
  if nomsg=0 then call wto 'TCP Server 'svrname' has been closed, port 'port
return 0
/* ---------------------------------------------------------------------
 * TCP Event Handler
 * ---------------------------------------------------------------------
 */
EventHandler:
  stopServer=0
  do forever
     event = tcpwait(timeout)
     if event <= 0 then call eventerror event
     select
        when event = #receive then call _#receive _fd
        when event = #connect then call _#connect _fd
        when event = #timeout then call _#timeout
        when event = #close   then call _#close _fd
        when event = #stop    then leave
        when event = #error   then call eventError
        otherwise  call eventError
     end
     if stopServer=1 then leave
  end
  call _#stop     /* is /F console cmd */
return
/* ---------------------------------------------------------------------
 * Time out
 * ---------------------------------------------------------------------
 */
_#timeout:
  parse arg #fd
  newtimeout=0
  rrc=TCPtimeout()
  if datatype(newtimeout)='NUM' & newtimeout>0 then do
     timeout=newtimeout
     call _#SVRMSG 1,'Timeout set to 'timeout
     if nomsg=0 then call wto 'Timeout set to 'timeout
  end
  if rrc=0 then return 0
  if rrc=8 then stopServer=1
return 0
/* ---------------------------------------------------------------------
 * Connect
 * ---------------------------------------------------------------------
 */
_#connect:
  parse arg #fd
  rrc=TCPconnect(#fd)
  if rrc=0 then return 0
  if rrc=4 then call _#close #fd
  if rrc=8 then stopServer=1
return 0
/* ---------------------------------------------------------------------
 * Receive Input
 * ---------------------------------------------------------------------
 */
_#receive:
  parse arg #fd
  dlen=TCPReceive(#fd)   /* Anzahl Byte */
  adata=a2e(_data)
/*  call _#SVRMSG 1,'Data from Client ' */
  if pos('/CANCEL',_data)>0 then StopServer=1 /* shut down server */
  if pos('/CANCEL',adata)>0 then StopServer=1 /* shut down server */
  if pos('/QUIT',_data)>0 | pos('/QUIT',adata)>0 then do
     call _#close #fd
     return 0
  end
  newtimeout=0
  rrc=TCPData(#fd,_data,adata)
  if datatype(newtimeout)='NUM' & newtimeout>0 then do
     timeout=newtimeout
     call _#SVRMSG 1,'Timeout set to 'timeout
     if nomsg=0 then call wto 'Timeout set to 'timeout
  end
  if rrc=0 then return 0
  if rrc=4 then call _#close #fd
  if rrc=8 then stopServer=1
return 0
/* ---------------------------------------------------------------------
 * Close Client
 * ---------------------------------------------------------------------
 */
_#close:
  parse arg #fd
  call _#SVRMSG 1,"close event from client Socket "#fd
  if tcpclose(#fd)=0 then call _#SVRMSG 1,"Client Socket "#fd" closed"
     else call _#SVRMSG 8,"Client Socket "#fd" can't be closed"
  rrc=TCPcloseS(#fd)   /* handle socket close  */
  if rrc=0 then return 0
  if rrc=8 then stopServer=1
return 0
/* ---------------------------------------------------------------------
 * Shut Down
 * ---------------------------------------------------------------------
 */
_#stop:
  call _#SVRMSG 1,"shut down event from client Socket "_fd
  call tcpTerm()
  call TCPshutdown   /* User's shut down processing */
return
/* ---------------------------------------------------------------------
 * Event Error
 * ---------------------------------------------------------------------
 */
eventError:
  if arg(1)<>'' then CALL _#SVRMSG 8,"TCPWait() error: "event
  else CALL _#SVRMSG 8,'TCP error: 'event
  call tcpTerm()
return 8
/* ---------------------------------------------------------------------
 * Set Message and Error Code
 * ---------------------------------------------------------------------
 */
_#SVRMSG:
parse arg _mslv
  if _mslv>=mslv | _mslv=0 then do           /* 0 is essential message */
     if _FD='_FD' then _fd=' '
     say time('L')' 'tcpmsg._mslv' 'port' 'right(_fd,4)' 'svrname' 'arg(2)
     call log tcpmsg._mslv' 'port' 'right(_fd,4)' 'svrname' 'arg(2)
  end
  if _mslv>maxrc then maxrc=_mslv
return _mslv

/* -------------------------------------------------------------------
 * Perform Console command and return associated Master TT Entries
 * ................................. Created by PeterJ on 19. May 2021
 * -------------------------------------------------------------------
 */
rxConsol: procedure expose console.
  parse upper arg cmd,wait4
/* .....  Send operator command  ............................ */
  call console(cmd)
  if datatype(wait4)<>'NUM' then wait4=300
  call wait(wait4)
  jobnum=MVSvar('JOBNUMBER')
  if arg(3)='STEM' then return console_slow()
  return console_fast()
/* -------------------------------------------------------------------
 * Running Console in ARRAY mode is much faster
 * -------------------------------------------------------------------
 */
console_fast:
  jnum=substr(jobnum,4)+0
  if __sysvar('SYSTSO')=1 then jbn='TSU'
     else jbn='JOB'
  jobn=jbn||right(jnum,5)
  cnum=2
/* .....  Check Trace Table for result  ..................... */
  mtt_sarray=screate(2000)
  _lines=mttx(1,mtt_sarray)     /* 1: build new, array is: mtt_sarray  */
  ssi=ssearch(mtt_sarray,jobn)
  _line=sget(mtt_sarray,ssi)
  if pos(cmd,_line)==0 then return 8
  console.1=_line
  _line=sget(mtt_sarray,ssi-1)
  console.2=_line
  trnum=lastword(_line)
  do k=ssi-2 to 1 by -1
     _line=sget(mtt_sarray,k)
     if word(_line,1)<>trnum then iterate
     cnum=cnum+1
     console.cnum=_line
  end
  console.0=cnum
return 0
/* -------------------------------------------------------------------
 * Running Console in STEM mode is slower
 * -------------------------------------------------------------------
 */
console_slow:
  console.0=0
/* .....  Check Trace Table for result  ..................... */
  call mtt()
  if _findTTEntry()<0 then return 8
/* .....  Pick up all TT entries after entry ................ */
  console.1=_line._tti
  cnum=1
  do k=_tti+1 to _line.0
     if strip(_line.k)='' then iterate
     if cnum=1 then do
 /*  0000 10.54.40 TSU 4344
     0000 10.54.40
  */
        cnum=cnum+1
        console.cnum=_line.k
        trnum=lastword(_line.k)
        if datatype(trnum)<>'NUM' then trnum=-1
        iterate
     end
     if trnum>0 then if word(_line.k,1)<>trnum then iterate
     cnum=cnum+1
     console.cnum=_line.k
  end
  console.0=cnum
return 0
/* -------------------------------------------------------------------
 * Find TT Entry with the sent operator command
 * -------------------------------------------------------------------
 */
_findTTEntry:
/* ...  Find job-/tso number which requested the command  ... */
  do _tti=_line.0 to max(1,_line.0-100) by -1
     jobn=translate(substr(_line._tti,15,8),'0',' ')
     if jobn<>jobnum then iterate
     if substr(_line._tti,25)=cmd then leave
  end
  if jobn<>jobnum then return -8
return _tti
