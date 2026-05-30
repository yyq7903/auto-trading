@echo off
REM Chrome debugging port forwarder for WSL2
REM Run this as Administrator on Windows

REM Add port forwarding rule
netsh interface portproxy add v4tov4 listenport=19825 listenaddress=0.0.0.0 connectport=19825 connectaddress=127.0.0.1

REM Add firewall rule
netsh advfirewall firewall add rule name="Chrome Debug Port" dir=in action=allow protocol=TCP localport=19825

echo Done! Chrome debugging port is now accessible from WSL2.
pause
