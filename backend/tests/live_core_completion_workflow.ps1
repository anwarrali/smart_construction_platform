param([string]$BaseUrl = "http://localhost:8001/api/v1")

$ErrorActionPreference = "Stop"

function Login([string]$email, [string]$password = "password123") {
  $body = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"
  (Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body).access_token
}
function Headers([string]$token) { @{ Authorization = "Bearer $token" } }
function Send([string]$method, [string]$path, $body, [string]$token) {
  Invoke-RestMethod -Method $method -Uri "$BaseUrl$path" -Headers (Headers $token) -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 12)
}
function Get([string]$path, [string]$token) { Invoke-RestMethod -Uri "$BaseUrl$path" -Headers (Headers $token) }
function Expect([int]$status, [string]$method, [string]$path, $body, [string]$token) {
  try { Send $method $path $body $token | Out-Null; throw "Expected HTTP $status for $path" }
  catch { if ([int]$_.Exception.Response.StatusCode -ne $status) { throw } }
}
function Assert($condition, [string]$message) { if (-not $condition) { throw "ASSERTION FAILED: $message" } }
function Collection($value) { if ($value -is [array]) { $value | ForEach-Object { $_ } } else { $value } }

$run = [guid]::NewGuid().ToString("N").Substring(0, 8)
$admin = Login "admin@constro.io"
$pm = Login "pm@constro.io"
$projects = Get "/projects?limit=100" $pm
$project = $projects.data[0]
Assert $project "Assigned PM project missing"

$engineer = Send Post "/users" @{
  email="core.engineer.$run@example.com"; fullName="Core Internal Engineer $run"; role="engineer";
  organization="Contractor Organization"; engineerAffiliation="internal_engineer";
  engineerProfile=@{ discipline="civil" }
} $admin
$consultant = Send Post "/users" @{
  email="core.consultant.$run@example.com"; fullName="Core External Consultant $run"; role="consultant";
  organization="External Review Office"; engineerAffiliation="external_consultant";
  engineerProfile=@{ discipline="civil" }
} $admin
Send Put "/users/$($engineer.id)/activate" @{} $admin | Out-Null
Send Put "/users/$($consultant.id)/activate" @{} $admin | Out-Null
Send Post "/projects/$($project.id)/members" @{ userId=$engineer.id; roleOnProject="engineer"; assignmentTitle="Internal Civil Engineer"; projectDiscipline="civil" } $pm | Out-Null
Send Post "/projects/$($project.id)/members" @{ userId=$consultant.id; roleOnProject="consultant"; assignmentTitle="External Civil Reviewer"; projectDiscipline="civil" } $pm | Out-Null

$engineerToken = Login $engineer.email $engineer.temporaryPassword
Send Put "/users/change-password" @{ currentPassword=$engineer.temporaryPassword; newPassword="CoreTest#1234" } $engineerToken | Out-Null

$task = Send Post "/tasks" @{
  projectId=$project.id; name="Core completion task $run"; status="todo"; priority="high";
  discipline="civil"; assigneeIds=@($engineer.id); plannedStartDate="2026-08-14";
  plannedEndDate="2026-08-16"; dependencyIds=@()
} $pm
Assert ($task.durationDays -eq 3) "Inclusive task duration failed"
Send Put "/tasks/$($task.id)/progress" @{ progressPercentage=100 } $engineerToken | Out-Null
$task = Send Put "/tasks/$($task.id)/submit-review" @{} $engineerToken
Assert ($task.status -eq "under_review") "Engineer review submission failed"
Expect 400 Put "/tasks/$($task.id)/reject" @{ comments=""; rejectionReason="" } $pm
$task = Send Put "/tasks/$($task.id)/reject" @{ comments="Correct the concrete evidence"; rejectionReason="Correct the concrete evidence" } $pm
Assert ($task.status -eq "rework_required") "PM rejection did not require rework"
Send Put "/tasks/$($task.id)/progress" @{ progressPercentage=100 } $engineerToken | Out-Null
Send Put "/tasks/$($task.id)/submit-review" @{} $engineerToken | Out-Null
$task = Send Put "/tasks/$($task.id)/approve" @{ comments="Evidence verified" } $pm
Assert ($task.status -eq "done" -and $task.reviewStatus -eq "approved") "PM approval failed"
$reviews = @(Collection (Get "/tasks/$($task.id)/reviews" $pm))
Assert ($reviews.Count -eq 2 -and $reviews[0].reviewedBy.fullName) "Full review history identity failed"

$milestone = Send Post "/milestones" @{
  projectId=$project.id; name="Core milestone $run"; description="Integrated milestone";
  plannedDate="2026-08-16"; taskIds=@($task.id)
} $pm
Assert ($milestone.milestoneCode -match '^MLS-\d{3}$' -and $milestone.status -eq "completed" -and $milestone.progressPercentage -eq 100) "Milestone progress/status failed"
$gantt = Get "/scheduling/$($project.id)/gantt" $pm
$ganttMilestone = @($gantt.tasks | Where-Object id -eq $milestone.id)
Assert ($ganttMilestone.Count -eq 1 -and $ganttMilestone[0].type -eq "milestone" -and $ganttMilestone[0].dependencies -contains $task.id) "Gantt milestone integration failed"
$dashboard = Get "/dashboard/projects/$($project.id)" $pm
Assert ($dashboard.milestoneTotal -ge 1 -and $dashboard.milestoneCompleted -ge 1) "Dashboard milestone metrics failed"

$message = Send Post "/messages" @{ projectId=$project.id; receiverId=$engineer.id; content="Please review tomorrow's site plan." } $pm
Assert (-not $message.isRead -and $message.sender.fullName) "Message send response failed"
# The API must never expose conversations outside the authenticated user's sender/receiver scope.
$conversation = Get "/messages?project_id=$($project.id)&participant_id=$((Get '/auth/me' $pm).id)" $engineerToken
Assert ($conversation.items.id -contains $message.id) "Receiver conversation did not contain the message"
$read = Send Put "/messages/$($message.id)/read" @{} $engineerToken
Assert $read.isRead "Message read state failed"
$notifications = Get "/notifications?page=1&limit=100&project_id=$($project.id)" $engineerToken
Assert ($notifications.items.relatedEntityId -contains $message.id) "Message notification was not generated"

$restrictedProject = Send Post "/projects" @{ name="RBAC restricted $run"; status="planning" } $admin
Expect 403 Get "/milestones?project_id=$($restrictedProject.id)" $null $pm

$reset = Send Post "/users/$($engineer.id)/reset-password" @{} $admin
Assert ($reset.temporaryPassword -and $reset.mustChangePassword) "Administrator password reset failed"
$audits = @(Collection (Get "/audit-logs?limit=500" $admin))
Assert (@($audits | Where-Object { $_.entity_id -eq $milestone.id -and $_.entity_type -eq "milestone" }).Count -ge 1) "Milestone audit log missing"
Assert (@($audits | Where-Object { $_.entity_id -eq $message.id -and $_.entity_type -eq "message" }).Count -ge 1) "Message audit log missing"
Assert (@($audits | Where-Object { $_.entity_id -eq $engineer.id -and $_.action -eq "password_reset" }).Count -ge 1) "Password reset audit log missing"

Write-Output "CORE_COMPLETION_WORKFLOW_OK project=$($project.id) task=$($task.id) milestone=$($milestone.id) message=$($message.id)"
