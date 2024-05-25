# AUTOMVS.rexx

**AUTOMVS.rexx** is a rexx script for use on TK4- and TK5. The
purpose of this script is to be used by the automvs python library
to automate all the functions that this python library supports, remotely. 
You do not need to use the automvs python script to use this rexx script 
for automation. 

This script takes 3 optional arguments:

1. `-port` the port to open for client connections. Default `9856`
2. `-timeout` the number of seconds to timeout. Default `60`
3. `DEBUG` enable default logging. Default `False`

:warning: using the DEBUG option can create potentially thousands
of lines either in the TSO terminal or in JES2. Only use it if you're
making a bug report or trying to troubleshoot an issue.

## Requirements

1. A running TK4- or TK5 mvs
2. TCPIP support which requires running the following hercules command 
   before IPL: `facility enable HERC_TCPIP_EXTENSION` and 
   `facility enable HERC_TCPIP_PROB_STATE`
3. BREXX V2R5M3 or greater

## Instalation

Upload the REXX script to a dataset then run the script. If you wish to
run as a started task (**recommended**) then also upload the `AUTOMVS.jcl` to
`SYS2.PROCLIB`.

```
BREXX 'HERC01.TEST.CNTL(AUTOMVS)'
```

If you place AUTOMVS.rexx in a dataset in `SYSEXEC` (on TK5 these are 
`username.EXEC` and `SYS2.EXEC`) you can run it with `BREXX AUTOMVS`.

In this folder is a script called `UPLOAD.sh`. If you're running TK5, or 
you've already created `SYS2.EXEC` on TK4- you can run this script in this
folder to upload both AUTOMVS.rexx (to `SYS2.EXEC`) and AUTOMVS.jcl (to
`SYS2.PROCLIB`) with the following commands:

1. In the hercules console: `CODEPAGE  819/1047` Note: You only need to do 
   this once to install the scripts
2. In this REXX folder: `./UPLOAD.sh|ncat -vw1 ip.or.hostname.of.your.mvs 3505`

## Started Task

If you uploaded the `AUTOMVS.jcl` file and plan to use it you must either place
`AUTOMVS.rexx` in `SYS2.EXEC(AUTOMVS)` or edit the following line to point
to the correct dataset(member):

```jcl
//EXEC     DD  DSN=SYS2.EXEC(AUTOMVS),DISP=SHR
```

### Running the Started Task

You can run automvs from the hercules console with `/S AUTOMVS` or 
`/START AUTOMVS`. This will run with the defaul parameters of:

- DEBUG off
- PORT 9856
- TIMEOUT 60


If you wish to run with any of these options enabled you can pass
them on the console line when you start automvs:

- Enable debugging: `/s automvs,debug=debug`
- Use a different port: `/s automvs,port=9999`
- Set a shorter timeout: `/s automvs,timeout=30`
- All together: `/s automvs,debug=debug,port=9999,timeout=30`

#### Examples:

```
/s automvs
/22.15.52 STC   72  $HASP100 AUTOMVS  ON STCINRDR
/22.15.52 STC   72  $HASP373 AUTOMVS  STARTED
/22.15.52 STC   72  IEF403I AUTOMVS - STARTED - TIME=22.15.52
/22.15.52 STC   72  +AUTOMVS 22:15:52.837397 Arguments: -port 9856 -timeout 60
/22.15.52 STC   72  +AUTOMVS 22:15:52.838555 PORT set to 9856
/22.15.52 STC   72  +AUTOMVS 22:15:52.839529 TIMEOUT set to 60
/22.15.52 STC   72  +AUTOMVS 22:15:52.840574 Port set to: 9856 Timeout set to: 60
/22.15.52 STC   72  +AUTOMVS 22:15:52.841455 Running as user STC
/22.15.52 STC   72  +AUTOMVS 22:15:52.845188 ..BASIC 9856      AUTOMVS TCP Server start at Port: 9856
```

```
/start automvs,debug=debug
/22.23.16 STC   73  $HASP100 AUTOMVS  ON STCINRDR
/22.23.16 STC   73  $HASP373 AUTOMVS  STARTED
/22.23.16 STC   73  IEF403I AUTOMVS - STARTED - TIME=22.23.16
/22.23.16 STC   73  +AUTOMVS 22:23:17.009857 Arguments: DEBUG -port 9856 -timeout 60
/22.23.16 STC   73  +AUTOMVS 22:23:17.011052 PORT set to 9856
/22.23.16 STC   73  +AUTOMVS 22:23:17.012187 TIMEOUT set to 60
/22.23.16 STC   73  +AUTOMVS 22:23:17.013410 Port set to: 9856 Timeout set to: 60
/22.23.16 STC   73  +AUTOMVS 22:23:17.014370 Debug log enabled
/22.23.16 STC   73  +AUTOMVS 22:23:17.015692 Running as user STC
/22.23.16 STC   73  +AUTOMVS 22:23:17.019817 ..BASIC 9856      AUTOMVS TCP Server start at Port: 9856
```

### Stopping the Started Task

To turn off AUTOMVS you can either issue the operator stop command
in the hercules console: `/STOP AUTOMVS` or, when logged in to
AUTOMVS, issue the `/SHUTDOWN` command. 

```
/stop automvs
/22.21.16 STC   72  +AUTOMVS 22:21:16.775661 Shutting Down AUTOMVS
/22.21.16 STC   72  IEF404I AUTOMVS - ENDED - TIME=22.21.16
/22.21.16 STC   72  $HASP395 AUTOMVS  ENDED
/22.21.16 STC   72  $HASP150 AUTOMVS  ON PRINTER2        76 LINES
/22.21.16           $HASP160 PRINTER2 INACTIVE - CLASS=Z
/22.21.16 STC   72  $HASP250 AUTOMVS  IS PURGED
```

## Using

AUTOMVS uses `/` commands and returns the results of that command
as ASCII. Multiple commands have been created. 

This script only allows one connection at a time. 

:warning: This script requires read access to the RAKF datasets, as such
only users in the `RAKFADM` group can logon as they could use
this script to download the RAKF database. 

## Commands

AUTOMVS uses various `/` commands to download files, check the MTT log, etc.

Except for `/LOGON` `/QUIT` and `/SHUTDOWN` all commands return a `--- DONE`
when done sending records. If an error is encountered an error message is 
sent that begins with `Error:`.

### /LOGON username password_hash

Required Arguments: USERNAME PASSWORD

The `/LOGON` command requires a username and a password. The password must
be sent as a JAVA hash. The script then compares the username and hash and
group membership to the RAKF database and if the username and password are
valid, and the user is in the `RAKFADM` group, returns the message `LOGON OK`

```
$ ncat test.server.tk4 9856
Welcome to AUTOMVS REXX Server: v0.0.5
Please /LOGON to continue
/LOGON HERC01 1504811420
LOGON OK
```

If an invalid username/password, or if the user is not in the RAKFADM group
the following message is returned

```
Logon Failed: Username/password invalid or user not in appropriate group
```

After 3 failed logon attempts the client is disconnected.

### /QUIT

Required Arguments: None

This command logs off and disconnects the current client.

```
/quit
Goodbye
```

### /SHUTDOWN

Required Arguments: None

This command logs off and disconnects the current client and shutsdown
the AUTOMVS script.

### /FILE `dataset[(member)]`

Required Argument: A sequential dataset or partitioned dataset and member

The `/FILE` command, when given a sequential or partitioned dataset and
member, returns the file as a base64 encoded string.

The maximum file size is 1.5MB, this is adjustible in the script but larger
file sizes may cause the script to crash as it runs out of memory. 

```
/file brexx.build.loadlib(svc)
--- Sending BASE64 Encoded File
AsXixEBAQEBAQAAQQEAAAeLlw0BAQEBAAAAAAEAAAJBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBA
QEBAQEBAQEBAQEBA4uXD8PDw8PEC4+fjQAAAAEBAADhAQAABkOzQDBjPUNDATBgtQdDASFDSAAgYsZhH
sABYBQAAWBYAAFj3AABEQMBEUPcAAFAWAABQBQAAWN3i5cPw8PDw8gLj5+NAAAA4QEAADkBAAAEABFjt
AAyYHNAYB/4KAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQOLlw/Dw8PDz
AsXVxEAAAABAQEBAQEAAAUBAQEBAQEBAQEBAQEBAQEDx9ff08eLD8fDzQPDy8PHy9PH09EBAQEBAQEBA
QEBAQEBAQEBAQEBA4uXD8PDw8PQ=                                                    
--- DONE
```

### /WAITFOR string

Required Arguments: String to wait for

Waits `timeout` (default 60) seconds for a string to appear in the master trace
log. 

```
/WAITFOR $HASP000 NO ACTIVE JOBS
--- Waiting 60 seconds for $HASP000 NO ACTIVE JOBS
--- DONE
/WAITFOR UNFINDABLE STRING
--- Waiting 60 seconds for UNFINDABLE STRING
Error: string not found in MTT: UNFINDABLE STRING
```

### /JOB JOBNAME [DEBUG TIMEOUT=xx]

Required Argument: A job name

Optional Arguments:

- `DEBUG` returns the full JES2 log from the MTT
- `TIMEOUT=` optional timeout in seconds to wait for a job to finish, 
  default is the default timeout

This command waits `timeout` seconds for the required `JOBNAME` to END 
or PURGE. It returns a CSV which consists of the job number, job name, 
step, procedure, program name, and return code. 

If the optional argument `DEBUG` is received it returns the JES2 MTT LOG
before returning the CSV.

```
/JOB RELEASE DEBUG
--- *JOBLOG* Full Log
*JOBLOG* 0200 16.41.17 JOB  122  $HASP100 RELEASE  ON READER1     Build BREXX Release
*JOBLOG* 4000 16.41.17 JOB  122  $HASP373 RELEASE  STARTED - INIT  1 - CLASS A - SYS TK4-
*JOBLOG* 4000 16.41.17 JOB  122  IEF403I RELEASE - STARTED - TIME=16.41.17
*JOBLOG* 0004 16.41.17 JOB  122  IEFACTRT - Stepname  Procstep  Program   Retcode
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    DLLINKLI            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    DLLINKLI            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    DLXMIT              IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    DLINSTAL            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    BRLINKLB            IEFBR14   RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    DLJCL               IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.17 JOB  122  RELEASE    JCL                 PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    DLSAMPLE            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    SAMPLES             PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    DLRXLIB             IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    RXLIB               PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    DLCMDLIB            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.18 JOB  122  RELEASE    CMDLIB              PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.19 JOB  122  RELEASE    DLPROCLI            IDCAMS    RC= 0000
*JOBLOG* 0004 16.41.19 JOB  122  RELEASE    PROCLIB             PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.19 JOB  122  RELEASE    BRAPFLNK            IEFBR14   RC= 0000
*JOBLOG* 0004 16.41.19 JOB  122  RELEASE    APFCOPY             IEBCOPY   RC= 0004
*JOBLOG* 0004 16.41.20 JOB  122  RELEASE    NOAPFCPY            IEWL      RC= 0000
*JOBLOG* 0004 16.41.20 JOB  122  RELEASE    STEP0B              IKJEFT01  RC= 0000
*JOBLOG* 0004 16.41.20 JOB  122  RELEASE    BRINSTAL            PDSLOAD   RC= 0000
*JOBLOG* 0004 16.41.20 JOB  122  RELEASE    XMITLLIB            XMIT370   RC= 0000
*JOBLOG* 0004 16.41.21 JOB  122  RELEASE    XMITAPF             XMIT370   RC= 0000
*JOBLOG* 0004 16.41.21 JOB  122  RELEASE    XMITJCL             XMIT370   RC= 0000
*JOBLOG* 0004 16.41.21 JOB  122  RELEASE    XMITSAMP            XMIT370   RC= 0000
*JOBLOG* 0004 16.41.22 JOB  122  RELEASE    XMITRXLI            XMIT370   RC= 0000
*JOBLOG* 0004 16.41.22 JOB  122  RELEASE    XMITCMDL            XMIT370   RC= 0000
*JOBLOG* 0004 16.41.22 JOB  122  RELEASE    XMITPROC            XMIT370   RC= 0000
*JOBLOG* 0004 16.41.24 JOB  122  RELEASE    XMITRLSE            XMIT370   RC= 0000
*JOBLOG* 4000 16.41.24 JOB  122  IEF404I RELEASE - ENDED - TIME=16.41.24
*JOBLOG* 4000 16.41.24 JOB  122  $HASP395 RELEASE  ENDED
*JOBLOG* 0200 16.41.24 JOB  122  $HASP150 RELEASE  ON PRINTER1     3,948 LINES
*JOBLOG* 0200 16.41.24 JOB  122  $HASP250 RELEASE  IS PURGED
--- *JOBLOG* Done
--- Job Results (28)
122 , RELEASE  ,  DLLINKLI,          ,IDCAMS,0000
122 , RELEASE  ,  DLLINKLI,          ,IDCAMS,0000
122 , RELEASE  ,  DLXMIT  ,          ,IDCAMS,0000
122 , RELEASE  ,  DLINSTAL,          ,IDCAMS,0000
122 , RELEASE  ,  BRLINKLB,          ,IEFBR14,0000
122 , RELEASE  ,  DLJCL   ,          ,IDCAMS,0000
122 , RELEASE  ,  JCL     ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLSAMPLE,          ,IDCAMS,0000
122 , RELEASE  ,  SAMPLES ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLRXLIB ,          ,IDCAMS,0000
122 , RELEASE  ,  RXLIB   ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLCMDLIB,          ,IDCAMS,0000
122 , RELEASE  ,  CMDLIB  ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLPROCLI,          ,IDCAMS,0000
122 , RELEASE  ,  PROCLIB ,          ,PDSLOAD,0000
122 , RELEASE  ,  BRAPFLNK,          ,IEFBR14,0000
122 , RELEASE  ,  APFCOPY ,          ,IEBCOPY,0004
122 , RELEASE  ,  NOAPFCPY,          ,IEWL,0000
122 , RELEASE  ,  STEP0B  ,          ,IKJEFT01,0000
122 , RELEASE  ,  BRINSTAL,          ,PDSLOAD,0000
122 , RELEASE  ,  XMITLLIB,          ,XMIT370,0000
122 , RELEASE  ,  XMITAPF ,          ,XMIT370,0000
122 , RELEASE  ,  XMITJCL ,          ,XMIT370,0000
122 , RELEASE  ,  XMITSAMP,          ,XMIT370,0000
122 , RELEASE  ,  XMITRXLI,          ,XMIT370,0000
122 , RELEASE  ,  XMITCMDL,          ,XMIT370,0000
122 , RELEASE  ,  XMITPROC,          ,XMIT370,0000
122 , RELEASE  ,  XMITRLSE,          ,XMIT370,0000
--- DONE
/JOB RELEASE
--- Job Results (28)
122 , RELEASE  ,  DLLINKLI,          ,IDCAMS,0000
122 , RELEASE  ,  DLLINKLI,          ,IDCAMS,0000
122 , RELEASE  ,  DLXMIT  ,          ,IDCAMS,0000
122 , RELEASE  ,  DLINSTAL,          ,IDCAMS,0000
122 , RELEASE  ,  BRLINKLB,          ,IEFBR14,0000
122 , RELEASE  ,  DLJCL   ,          ,IDCAMS,0000
122 , RELEASE  ,  JCL     ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLSAMPLE,          ,IDCAMS,0000
122 , RELEASE  ,  SAMPLES ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLRXLIB ,          ,IDCAMS,0000
122 , RELEASE  ,  RXLIB   ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLCMDLIB,          ,IDCAMS,0000
122 , RELEASE  ,  CMDLIB  ,          ,PDSLOAD,0000
122 , RELEASE  ,  DLPROCLI,          ,IDCAMS,0000
122 , RELEASE  ,  PROCLIB ,          ,PDSLOAD,0000
122 , RELEASE  ,  BRAPFLNK,          ,IEFBR14,0000
122 , RELEASE  ,  APFCOPY ,          ,IEBCOPY,0004
122 , RELEASE  ,  NOAPFCPY,          ,IEWL,0000
122 , RELEASE  ,  STEP0B  ,          ,IKJEFT01,0000
122 , RELEASE  ,  BRINSTAL,          ,PDSLOAD,0000
122 , RELEASE  ,  XMITLLIB,          ,XMIT370,0000
122 , RELEASE  ,  XMITAPF ,          ,XMIT370,0000
122 , RELEASE  ,  XMITJCL ,          ,XMIT370,0000
122 , RELEASE  ,  XMITSAMP,          ,XMIT370,0000
122 , RELEASE  ,  XMITRXLI,          ,XMIT370,0000
122 , RELEASE  ,  XMITCMDL,          ,XMIT370,0000
122 , RELEASE  ,  XMITPROC,          ,XMIT370,0000
122 , RELEASE  ,  XMITRLSE,          ,XMIT370,0000
--- DONE
```

### /PURGE JOBNAME

Required Arguments: 

- JOBNUM the job number
- JOBNAME the job name

This command will PURGE the given jobname from the queue. 

```
/PURGE 130 TESTJOB
--- Purging JOB TESTJOB  #130
--- DONE
```

### /OPER command

Required Arguments: string with MVS operator commands

Run MVS operator console commands.

```
/OPER $D A
--- Log for oper command: $D A (2)
0000 20.55.51 STC   68  $D A
0004 20.55.51           $HASP000 NO ACTIVE JOBS
--- DONE
```

### /HERCULES command

Required Arguments: string with hercules console commands

Runs hercules commands and returns the output:

```
/HERCULES uptime
--- Log for oper command: uptime
HHC02208I Uptime 20:24:24
COMMAND COMPLETE. RC = 000
--- DONE
```