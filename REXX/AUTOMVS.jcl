//AUTOMVS PROC PORT='9856',DEBUG='',TIMEOUT=60
//* *********************************************
//*
//*  This is the procedure to run automvs
//*  Install to SYS2.PROCLIB(AUTOMVS)
//*  and run with /s automvs
//*
//*  PORT is the port to use, default is 3702
//*  DEBUG enables verbose logging to WTO and SYSOUT
//*        To enable set to DEBUG
//*
//*  Usage: /S AUTOMVS
//*         /S AUTOMVS,PORT=5555
//*         /S AUTOMVS,PORT=5555,DEBUG=DEBUG
//*
//* *********************************************
//EXEC     EXEC PGM=IKJEFT01,
//         PARM='BREXX EXEC &DEBUG -port &PORT -timeout &TIMEOUT',
//         REGION=8192K
//EXEC     DD  DSN=SYS2.EXEC(AUTOMVS),DISP=SHR
//STDIN    DD  DUMMY
//STDOUT   DD  SYSOUT=*,DCB=(RECFM=FB,LRECL=140,BLKSIZE=5600)
//STDERR   DD  SYSOUT=*,DCB=(RECFM=FB,LRECL=140,BLKSIZE=5600)
//SYSPRINT DD  SYSOUT=*
//SYSTSPRT DD  SYSOUT=*
//SYSTSIN  DD  DUMMY
//STDIN    DD  DUMMY
