$runs = 50

for ($i = 1; $i -le $runs; $i++) {

    $output = python .\midterm_2.py | Select-String "Average data packet delay:" | Select-String -Pattern "\d+"
    if ($output -match 'Average data packet delay:\s*([\d\.]+)') {
        $number = [double]$Matches[1]
        Write-Host "$number"
    }
}
