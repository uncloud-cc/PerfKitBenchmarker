$url = 'https://download.microsoft.com/download/6/e/7/6e72dddf-dfa4-4889-bc3d-e5d3a0fd11ce/SQLServer2019-KB5027702-x64.exe'
$dest = 'c:\scripts\SQLServer2019-KB5027702-x64.exe'

# Download the file
(New-Object System.Net.WebClient).DownloadFile($url, $dest)

c:\scripts\SQLServer2019-KB5027702-x64.exe /q /IAcceptSQLServerLicenseTerms /Action=Patch /InstanceName=MSSQLSERVER
