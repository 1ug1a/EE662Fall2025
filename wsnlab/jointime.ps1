$totalTime = 0
$runs = 50

for ($i = 1; $i -le $runs; $i++) {
    
    $output = python .\midterm_2.py | Select-String "Average join time:" | Select-String -Pattern "\d+"
    if ($output -match 'Average join time:\s*([\d\.]+)') {
        $number = [double]$Matches[1]
        Write-Host "$number"
        $totalTime += [double]$number
    }
}

$avg = $totalTime / $runs
Write-Host "The true average over $runs runs is: $avg"