$runs = 60

for ($i = 1; $i -le $runs; $i++) {

    $output = python .\midterm_2.py | Select-String "Average rejoin time:" | Select-String -Pattern "\d+"
    if ($output -match 'Average rejoin time:\s*([\d\.]+)') {
        $number = [double]$Matches[1]
        Write-Host "$number"
    }
}
