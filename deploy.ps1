param(
    [string]$Message = "Auto-deploy from opencode"
)

$ErrorActionPreference = "Stop"

git add -u
git commit -m "$Message" 2>$null
if ($?) {
    Write-Host "Committed: $Message"
} else {
    Write-Host "Nothing to commit" -ForegroundColor Yellow
}

git push origin main 2>&1
if ($?) {
    Write-Host "Pushed to origin/main. Railway will auto-deploy." -ForegroundColor Green
} else {
    Write-Host "Push failed. Check git status." -ForegroundColor Red
}
