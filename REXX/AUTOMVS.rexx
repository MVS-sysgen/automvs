/* This REXX Script is used by the AUTOMVS Python library to automate */
/* Checking the status of jobs, obatining the results of each step,   */
/* returning a base64 encoded version of any file and returning the   */
/* job log                                                            */

VERSION = '0.0.5'

/* When launching the script optional arguments are: -port - the port */
/* to use (default 3207), -timeout (default 60 seconds), the timeout  */
/* to read the socket, and an optional DEBUG flag (default False). You*/
/* can specify one, all or none of these arguments.                   */


/* /LOGON: Takes a username and password, this user and password must */
/*        be in the RAKF database to use this script and be in the    */
/*        ADMIN group                                                 */
/*        e.g. /LOGON HERC01 CUL8TR                                   */
/*        Returns 'OK!' if logon is succesful                         */

/* /JOB: Take a job name or jobnum and return the results of each     */
/* step. The format of the return is a CSV with jobnum, jobname,      */
/* stepname, progname and rc. If the optional 'DEBUG' argument is     */
/* passed the console log returned as well.                           */
/*       e.g. /JOB jobname or /JOB jobname DEBUG                      */

/* /FILE <filename>: returns a file as a base64 encoded string can be */
/* either a sequential file or a member of a PDS                      */
/*       e.g. /FILE TESTING.TEST(MEMBER)                              */
/*            /FILE THIS.IS.A.TEST                                    */

parse arg arguments
call argparse arguments

call log 'Running as user' userid()

  /*         */
 /* Globals */
/*         */

attempts = 0
logon = 0
connected = 0

/* Call TCPSF to start the server */

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
        parse var values jobname sendlog .

        if upper(sendlog) = 'DEBUG' then do
          call verbose 'TCPData:' #fd '/JOB - Detailed log requested'
          sendlog = 1
        end

        if length(jobname) > 0 then do
          call check_job #fd jobname sendlog
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
        do i=1 to herc_command.0
          call send #fd herc_command.i
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
        else do
          DO UNTIL EOF(dsn_hndl)=1
            BIN_FILE = BIN_FILE || READ(dsn_hndl)
          END
          R = CLOSE(dsn_hndl)
          call log "Sending '"dsn"' Size: " length(BIN_FILE)
          call send #fd '--- Sending BASE64 Encoded File'
          call send #fd BASE64ENC(BIN_FILE)
          call send #fd '--- DONE'
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

    if length(msg) < 80 then do
      if right(msg, 1) \= '25'x then msg = msg || '25'x
      SendLength=TCPSEND(#fd, e2a(msg))

      if SendLength = -1 then
        call log 'Socket Error sending to' #fd sendlength
      if SendLength = -2 then
        call log 'Client not receiving data' #fd sendlength
    end
    else do /* Larger files needs to be broken up */
        do x = 1 to length(msg) by 80
          bytes = substr(msg, x, 80)
          SendLength=TCPSEND(#fd, e2a(bytes|| '25'x))

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
    port = 3702 /* Default port */
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
      call send #fd 'error: job' jobname '('jobnum') ENDED/PURGED not found'
      return
    end

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

  if full_log = 1 then call send #fd '--- Full Log'

  do i=1 to _line.0

    if pos('JOB'RIGHT(JOBNUM,5),_line.i) > 0 then do
      if full_log = 1 then do
        call send #fd _line.i
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

      if _jtype \= '0004' then iterate /* skip error messages */

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

  if full_log = 1 then call send #fd '--- Done'

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
  MARRAY=SCREATE(4096)
  /* Search the MTT for the job read message */
  result = MTTX('R',MARRAY,srch_for)
  T  = time('S')
  DO WHILE result = 0
    result = MTTX('R',MARRAY,srch_for)
    if time('s') - T >= timeout then do
      err = 'Error:' "'"srch_for"'" 'not found after' timeout 'seconds'
      call verbose 'wait_for_string:' err
      call send #fd err
      return
    end
  end
  call send #fd '--- DONE'
  call sfree(marray)
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

    IF CUR_USER = UPPER(username) & CUR_PASS = UPPER(PASSWORD) then do
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
    call send #fd 'Logon Failed: Username/password invalid or user'||,
                  ' not in appropriate group'
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
    if pos('$HASP100 '||_jname,_line.i)	>	0	then	do
      call verbose 'get_jobnum: Job' _jname 'found:' _line.i
      parse var _line.i  . . . _jobnum .
      leave
    end
  end

  return _jobnum


failed_logon:
    parse var #fd command
    call verbose 'failed_logon:' #fd command '- access denied'
    call verbose 'failed_logon:' #fd command '- access denied'
    call send #fd 'Access Denied'
    call send #fd 'Please /LOGON to continue'

check_logon:
  parse var #fd command
  call verbose "check_logon: Checking if client is logged in"
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

