$runs = 60

for ($i = 1; $i -le $runs; $i++) {

    $output = python .\midterm_2.py | Select-String "Number of disconnected active nodes:" | Select-String -Pattern "\d+"
    if ($output -match 'Number of disconnected active nodes:\s*([\d\.]+)') {
        $number = [double]$Matches[1]
        Write-Host "$number"
    }
}
