@echo off
rem Run the cocotb + GHDL test suites from Windows through WSL (Ubuntu).
rem   sim\run_all.cmd            all suites
rem   sim\run_all.cmd quick      unit + system tests
rem   sim\run_all.cmd --waves -k test_i2s
wsl -d Ubuntu --cd "%~dp0" -- bash ./run_all.sh %*
