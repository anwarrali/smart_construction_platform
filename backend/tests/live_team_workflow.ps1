$ErrorActionPreference = "Stop"
$base = "http://localhost:8000/api/v1"

function Login([string]$email, [string]$password) {
  $body = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"
  return Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body
}
function Headers($token) { return @{ Authorization = "Bearer $($token.access_token)" } }
function JsonPost($uri, $headers, $body) {
  return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 8)
}
function JsonPut($uri, $headers, $body) {
  return Invoke-RestMethod -Method Put -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 8)
}
function JsonPatch($uri, $headers, $body) {
  return Invoke-RestMethod -Method Patch -Uri $uri -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 8)
}
function Assert([bool]$condition, [string]$message) {
  if (-not $condition) { throw "ASSERTION FAILED: $message" }
}

$run = [guid]::NewGuid().ToString("N").Substring(0, 8)
$engineerEmail = "codex.teamtest.engineer.$run@example.com"
$consultantEmail = "codex.teamtest.consultant.$run@example.com"
$admin = Login "admin@constro.io" "password123"
$pm = Login "pm@constro.io" "password123"
$adminHeaders = Headers $admin
$pmHeaders = Headers $pm
$projectPage = Invoke-RestMethod -Uri "$base/projects?limit=100" -Headers $adminHeaders
$projectA = $projectPage.data[0]
$projectB = $projectPage.data[1]

$engineer = JsonPost "$base/users" $adminHeaders @{
  email=$engineerEmail; fullName="Workflow Civil Engineer $run"; role="engineer";
  phoneNumber="+970599100001"; organization="Main Contractor QA"; engineerAffiliation="main_contractor";
  engineerProfile=@{ discipline="civil" }
}
$consultant = JsonPost "$base/users" $adminHeaders @{
  email=$consultantEmail; fullName="Workflow Electrical Consultant $run"; role="consultant";
  phoneNumber="+970599100002"; organization="External Electrical QA"; engineerAffiliation="external_consultant";
  engineerProfile=@{ discipline="electrical" }
}
JsonPut "$base/users/$($engineer.id)/activate" $adminHeaders @{} | Out-Null
JsonPut "$base/users/$($consultant.id)/activate" $adminHeaders @{} | Out-Null
$engineerPersisted = Invoke-RestMethod -Uri "$base/users/$($engineer.id)" -Headers $adminHeaders
$consultantPersisted = Invoke-RestMethod -Uri "$base/users/$($consultant.id)" -Headers $adminHeaders
Assert ($engineerPersisted.role -eq "engineer" -and $engineerPersisted.engineerProfile.discipline -eq "civil" -and $engineerPersisted.engineerAffiliation -eq "main_contractor") "Internal Engineer account fields did not persist"
Assert ($consultantPersisted.role -eq "consultant" -and $consultantPersisted.engineerProfile.discipline -eq "electrical" -and $consultantPersisted.organization -eq "External Electrical QA") "External Consultant account fields did not persist"

$adminEngineerAvailable = Invoke-RestMethod -Uri "$base/projects/$($projectB.id)/available-team-members?search=$run&role=engineer&discipline=civil&affiliation=main_contractor" -Headers $adminHeaders
$adminConsultantAvailable = Invoke-RestMethod -Uri "$base/projects/$($projectB.id)/available-team-members?search=$run&role=consultant&discipline=electrical&affiliation=external_consultant" -Headers $adminHeaders
Assert ($adminEngineerAvailable.id -contains $engineer.id) "Backend filters did not return the Civil Engineer"
Assert ($adminConsultantAvailable.id -contains $consultant.id) "Backend filters did not return the Electrical Consultant"

$adminEngineerMembership = JsonPost "$base/projects/$($projectB.id)/members" $adminHeaders @{ userId=$engineer.id; roleOnProject="engineer"; assignmentTitle="Civil Project Engineer"; projectDiscipline="civil"; projectNotes="Admin assignment test" }
$adminConsultantMembership = JsonPost "$base/projects/$($projectB.id)/members" $adminHeaders @{ userId=$consultant.id; roleOnProject="consultant"; assignmentTitle="Electrical Technical Reviewer"; projectDiscipline="electrical"; projectNotes="Admin assignment test" }

$pmAvailable = Invoke-RestMethod -Uri "$base/projects/$($projectA.id)/available-team-members?search=$run" -Headers $pmHeaders
Assert (@($pmAvailable | Where-Object { $_.status -ne "active" -or $_.role -notin @("engineer","consultant") }).Count -eq 0) "PM eligible list contains an invalid role or inactive account"
Assert ($pmAvailable.id -contains $engineer.id -and $pmAvailable.id -contains $consultant.id) "PM cannot see both eligible test users"
$pmEngineerMembership = JsonPost "$base/projects/$($projectA.id)/members" $pmHeaders @{ userId=$engineer.id; roleOnProject="engineer"; assignmentTitle="Civil Site Engineer"; projectDiscipline="civil"; projectNotes="PM assignment test" }
$pmConsultantMembership = JsonPost "$base/projects/$($projectA.id)/members" $pmHeaders @{ userId=$consultant.id; roleOnProject="consultant"; assignmentTitle="Electrical Reviewer"; projectDiscipline="electrical"; projectNotes="PM assignment test" }

$duplicateStatus = 0
try { JsonPost "$base/projects/$($projectA.id)/members" $pmHeaders @{ userId=$engineer.id; roleOnProject="engineer" } | Out-Null }
catch { $duplicateStatus = [int]$_.Exception.Response.StatusCode }
Assert ($duplicateStatus -eq 409) "Duplicate active project membership was not rejected"

$teamA = Invoke-RestMethod -Uri "$base/projects/$($projectA.id)/members" -Headers $pmHeaders
Assert (@($teamA | Where-Object { $_.userId -eq $engineer.id -and $_.isActive }).Count -eq 1) "Engineer membership did not persist after refresh"
Assert (@($teamA | Where-Object { $_.userId -eq $consultant.id -and $_.isActive }).Count -eq 1) "Consultant membership did not persist after refresh"

JsonPatch "$base/projects/$($projectA.id)/members/$($engineer.id)/assignment" $pmHeaders @{ assignmentTitle="Lead Civil Site Engineer"; projectDiscipline="civil"; projectNotes="Site duty verified"; isSiteEngineer=$true } | Out-Null
$teamA = Invoke-RestMethod -Uri "$base/projects/$($projectA.id)/members" -Headers $pmHeaders
Assert (($teamA | Where-Object { $_.userId -eq $engineer.id }).isSiteEngineer -eq $true) "Site Engineer assignment did not persist"

$engineerLogin = Login $engineerEmail $engineer.temporaryPassword
$engineerHeaders = Headers $engineerLogin
JsonPut "$base/users/change-password" $engineerHeaders @{ currentPassword=$engineer.temporaryPassword; newPassword="TeamTest#1234" } | Out-Null
$notificationPage = Invoke-RestMethod -Uri "$base/notifications?page=1&limit=50&project_id=$($projectA.id)" -Headers $engineerHeaders
$siteNotification = $notificationPage.items | Where-Object { $_.title -eq "Site Engineer Assignment" } | Select-Object -First 1
$projectNotification = $notificationPage.items | Where-Object { $_.title -eq "Project Assignment" } | Select-Object -First 1
Assert ($null -ne $siteNotification -and $null -ne $projectNotification) "Required project/site notifications were not created"
JsonPut "$base/notifications/$($siteNotification.id)/read" $engineerHeaders @{} | Out-Null
$notificationPage = Invoke-RestMethod -Uri "$base/notifications?page=1&limit=50&project_id=$($projectA.id)" -Headers $engineerHeaders
Assert (($notificationPage.items | Where-Object { $_.id -eq $siteNotification.id }).isRead -eq $true) "Notification read state did not persist"

JsonPatch "$base/projects/$($projectA.id)/members/$($engineer.id)/assignment" $pmHeaders @{ isSiteEngineer=$false; assignmentTitle="Civil Project Engineer" } | Out-Null
$teamA = Invoke-RestMethod -Uri "$base/projects/$($projectA.id)/members" -Headers $pmHeaders
Assert (($teamA | Where-Object { $_.userId -eq $engineer.id }).isSiteEngineer -eq $false) "Site Engineer removal did not persist"

Invoke-RestMethod -Method Delete -Uri "$base/projects/$($projectA.id)/members/$($consultant.id)" -Headers $pmHeaders | Out-Null
$consultantStillExists = Invoke-RestMethod -Uri "$base/users/$($consultant.id)" -Headers $adminHeaders
Assert ($consultantStillExists.id -eq $consultant.id) "Removing project membership deleted the global Consultant"
$teamB = Invoke-RestMethod -Uri "$base/projects/$($projectB.id)/members" -Headers $adminHeaders
Assert (@($teamB | Where-Object { $_.userId -eq $consultant.id -and $_.isActive }).Count -eq 1) "Consultant membership in the other project was incorrectly removed"

$unassignedProject = JsonPost "$base/projects" $adminHeaders @{ name="Role Workflow Access Test $run"; description="Temporary RBAC verification"; status="planning" }
$unassignedStatus = 0
try { Invoke-RestMethod -Uri "$base/projects/$($unassignedProject.id)/available-team-members" -Headers $pmHeaders | Out-Null }
catch { $unassignedStatus = [int]$_.Exception.Response.StatusCode }
Assert ($unassignedStatus -eq 403) "PM was not denied team management for an unassigned project"

# API cleanup of memberships and temporary project. Global test accounts are
# removed by an exact database cleanup after audit/notification verification.
Invoke-RestMethod -Method Delete -Uri "$base/projects/$($projectA.id)/members/$($engineer.id)" -Headers $pmHeaders | Out-Null
Invoke-RestMethod -Method Delete -Uri "$base/projects/$($projectB.id)/members/$($engineer.id)" -Headers $adminHeaders | Out-Null
Invoke-RestMethod -Method Delete -Uri "$base/projects/$($projectB.id)/members/$($consultant.id)" -Headers $adminHeaders | Out-Null
Invoke-RestMethod -Method Delete -Uri "$base/projects/$($unassignedProject.id)" -Headers $adminHeaders | Out-Null

[pscustomobject]@{
  Run=$run; EngineerId=$engineer.id; ConsultantId=$consultant.id;
  EngineerEmail=$engineerEmail; ConsultantEmail=$consultantEmail;
  MembershipIds=@($adminEngineerMembership.id,$adminConsultantMembership.id,$pmEngineerMembership.id,$pmConsultantMembership.id) -join ",";
  ProjectA=$projectA.id; ProjectB=$projectB.id;
  AccountPersistence=$true; BackendFiltering=$true; AdminAssignment=$true; PmAssignment=$true;
  DuplicateBlocked=$true; SiteEngineerPersistence=$true; NotificationAndReadState=$true;
  ConsultantGlobalAccountPreserved=$true; MultiProjectMembership=$true; UnassignedProjectDenied=$true
} | ConvertTo-Json
