param([string]$BaseUrl = "http://localhost:8001/api/v1")

$ErrorActionPreference = "Stop"

function Login([string]$email) {
  $body = "username=$([uri]::EscapeDataString($email))&password=password123"
  (Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body).access_token
}

function Headers([string]$token) { @{ Authorization = "Bearer $token" } }
function GetApi([string]$path, [string]$token) { Invoke-RestMethod -Uri "$BaseUrl$path" -Headers (Headers $token) }
function SendApi([string]$method, [string]$path, $body, [string]$token) {
  Invoke-RestMethod -Method $method -Uri "$BaseUrl$path" -Headers (Headers $token) -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 10)
}
function ExpectStatus([int]$status, [string]$method, [string]$path, $body, [string]$token) {
  try { SendApi $method $path $body $token | Out-Null; throw "Expected HTTP $status for $path" }
  catch { if ([int]$_.Exception.Response.StatusCode -ne $status) { throw } }
}
function Assert($condition, [string]$message) { if (-not $condition) { throw $message } }
function Collection($value) { if ($value -is [array]) { $value | ForEach-Object { $_ } } else { $value } }

$admin = Login "admin@constro.io"
$pm = Login "pm@constro.io"
$users = @(Collection (GetApi "/users" $admin))
$owner = $users | Where-Object email -eq "owner@constro.io" | Select-Object -First 1
$manager = $users | Where-Object email -eq "pm@constro.io" | Select-Object -First 1
$engineer = $users | Where-Object email -eq "civil@constro.io" | Select-Object -First 1
$consultant = $users | Where-Object email -eq "consultant@constro.io" | Select-Object -First 1
$outsideEngineer = $users | Where-Object email -eq "mech@constro.io" | Select-Object -First 1
Assert ($owner -and $manager -and $engineer -and $consultant -and $outsideEngineer) "Required real users were not found"

$run = [guid]::NewGuid().ToString("N").Substring(0, 8)
$project1 = SendApi Post "/projects" @{ name="Workflow Project $run"; ownerId=$owner.id; projectManagerId=$manager.id; status="active" } $admin
$project2 = SendApi Post "/projects" @{ name="Transfer Project $run"; ownerId=$owner.id; projectManagerId=$manager.id; status="active" } $admin

$engMembership = SendApi Post "/projects/$($project1.id)/members" @{ userId=$engineer.id; roleOnProject="engineer"; assignmentTitle="Civil Execution Engineer"; projectDiscipline="civil"; isSiteEngineer=$true } $admin
$consultMembership = SendApi Post "/projects/$($project1.id)/members" @{ userId=$consultant.id; roleOnProject="consultant"; assignmentTitle="Design Reviewer"; projectDiscipline="architectural"; projectNotes="External design review" } $admin
$engMembership = SendApi Patch "/projects/$($project1.id)/members/$($engineer.id)/assignment" @{ assignmentTitle="Lead Site Engineer"; projectDiscipline="civil"; projectNotes="Coordinates site execution"; isSiteEngineer=$true } $admin
Assert ($engMembership.isSiteEngineer -and $engMembership.assignmentTitle -eq "Lead Site Engineer") "Admin project assignment edit did not persist"

$team = @(Collection (GetApi "/projects/$($project1.id)/members" $admin))
$eligible = @($team | Where-Object { $_.isActive -and $_.user.status -eq "active" -and $_.user.role -in @("engineer","consultant","project_manager") })
Assert (@($eligible | Where-Object userId -eq $engineer.id).Count -eq 1) "Project engineer was missing from real assignee members"
Assert (@($eligible | Where-Object userId -eq $consultant.id).Count -eq 1) "Project consultant was missing from real assignee members"
Assert (@($team | Where-Object userId -eq $outsideEngineer.id).Count -eq 0) "Unrelated engineer leaked into project membership"
Assert (($engMembership.user.fullName) -and ($engMembership.user.engineerProfile.discipline) -and ($engMembership.user.engineerAffiliation)) "Assignee identity metadata was incomplete"

$task1 = SendApi Post "/tasks" @{ projectId=$project1.id; name="Site Preparation"; status="backlog"; priority="high"; assigneeIds=@($engineer.id); discipline="civil"; plannedStartDate="2026-08-01"; plannedEndDate="2026-08-03"; dependencyIds=@() } $pm
Assert ($task1.taskCode -eq "TSK-001" -and $task1.durationDays -eq 3 -and @($task1.dependencies).Count -eq 0) "First task code, duration, or empty dependencies failed"
Assert (@($task1.assignees).Count -eq 1 -and $task1.assignees[0].fullName -eq $engineer.fullName) "Single assignee identity was not returned"
Assert ([guid]::Parse($task1.id)) "Task UUID was not preserved as the internal ID"
$engineerToken = Login "civil@constro.io"
$task1 = SendApi Put "/tasks/$($task1.id)/progress" @{ progressPercentage=10 } $engineerToken
Assert ($task1.progressPercentage -eq 10 -and $task1.status -eq "in_progress") "Assigned engineer could not update task progress"

$task2 = SendApi Post "/tasks" @{ projectId=$project1.id; name="Excavation"; status="backlog"; priority="critical"; assigneeIds=@($consultant.id); discipline="civil"; plannedStartDate="2026-08-04"; plannedEndDate="2026-08-07"; dependencyIds=@($task1.id) } $pm
Assert ($task2.taskCode -eq "TSK-002" -and $task2.durationDays -eq 4) "Second task code or inclusive duration failed"
Assert (@($task2.dependencies)[0].dependsOnTaskId -eq $task1.id) "Create-time dependency did not persist"

$task3 = SendApi Post "/tasks" @{ projectId=$project1.id; name="Foundation Coordination"; status="backlog"; priority="medium"; assigneeIds=@($engineer.id,$consultant.id); discipline="civil"; plannedStartDate="2026-08-08"; plannedEndDate="2026-08-08"; dependencyIds=@($task1.id,$task2.id) } $pm
Assert ($task3.taskCode -eq "TSK-003" -and $task3.durationDays -eq 1 -and @($task3.dependencies).Count -eq 2) "Multiple dependencies or one-day duration failed"
Assert (@($task3.assignees).Count -eq 2 -and @($task3.assigneeIds).Count -eq 2) "Multiple task assignees did not persist"

$task3 = SendApi Put "/tasks/$($task3.id)" @{ assigneeIds=@($engineer.id) } $pm
Assert (@($task3.assignees).Count -eq 1) "Removing one task assignee did not persist"
$task3 = SendApi Put "/tasks/$($task3.id)" @{ assigneeIds=@($engineer.id,$consultant.id) } $pm
Assert (@($task3.assignees).Count -eq 2) "Re-adding multiple task assignees did not persist"

$task3 = SendApi Put "/tasks/$($task3.id)" @{ dependencyIds=@($task2.id) } $pm
Assert (@($task3.dependencies).Count -eq 1) "Dependency removal through Edit Task did not persist"
$task3 = SendApi Put "/tasks/$($task3.id)" @{ dependencyIds=@($task1.id,$task2.id) } $pm
Assert (@($task3.dependencies).Count -eq 2) "Dependency re-add through Edit Task did not persist"

ExpectStatus 400 Put "/tasks/$($task1.id)" @{ dependencyIds=@($task2.id) } $pm
ExpectStatus 400 Put "/tasks/$($task1.id)" @{ dependencyIds=@($task1.id) } $pm
ExpectStatus 422 Put "/tasks/$($task3.id)" @{ dependencyIds=@($task1.id,$task1.id) } $pm
ExpectStatus 422 Put "/tasks/$($task3.id)" @{ assigneeIds=@($engineer.id,$engineer.id) } $pm
ExpectStatus 400 Post "/tasks" @{ projectId=$project1.id; name="Outside assignee"; status="backlog"; priority="low"; assigneeIds=@($outsideEngineer.id); dependencyIds=@() } $pm
SendApi Post "/projects/$($project1.id)/members" @{ userId=$outsideEngineer.id; roleOnProject="engineer"; assignmentTitle="Mechanical Coordination Engineer"; projectDiscipline="mechanical" } $admin | Out-Null
$task3 = SendApi Put "/tasks/$($task3.id)" @{ assigneeIds=@($engineer.id,$outsideEngineer.id) } $pm
Assert (@($task3.assignees).Count -eq 2 -and @($task3.assignees | Where-Object role -eq "engineer").Count -eq 2) "Multiple engineers on one task did not persist"

$temporary = SendApi Post "/tasks" @{ projectId=$project1.id; name="Temporary Deleted Task"; status="backlog"; priority="low"; dependencyIds=@() } $pm
Assert ($temporary.taskCode -eq "TSK-004") "Expected TSK-004 before delete"
Invoke-RestMethod -Method Delete -Uri "$BaseUrl/tasks/$($temporary.id)" -Headers (Headers $pm) | Out-Null
$next = SendApi Post "/tasks" @{ projectId=$project1.id; name="Non-Reused Task Code"; status="backlog"; priority="low"; dependencyIds=@() } $pm
Assert ($next.taskCode -eq "TSK-005") "Deleted task code was reused"

$otherTask = SendApi Post "/tasks" @{ projectId=$project2.id; name="Independent First Task"; status="backlog"; priority="low"; plannedStartDate="2026-09-01"; plannedEndDate="2026-09-01"; dependencyIds=@() } $pm
Assert ($otherTask.taskCode -eq "TSK-001") "Second project did not start independently at TSK-001"
ExpectStatus 400 Put "/tasks/$($task1.id)" @{ dependencyIds=@($otherTask.id) } $pm

$gantt = GetApi "/scheduling/$($project1.id)/gantt" $pm
$gantt2 = @($gantt.tasks) | Where-Object id -eq $task2.id | Select-Object -First 1
Assert ($gantt2.task_code -eq "TSK-002" -and @($gantt2.dependencies)[0] -eq $task1.id) "Gantt task code or persisted relationship failed"
$critical = GetApi "/scheduling/$($project1.id)/critical-path" $pm
Assert ($critical.projectDurationDays -eq 8) "Critical path did not use inclusive 3 + 4 + 1 durations"
Assert ((@($critical.criticalTasks | Select-Object -ExpandProperty taskCode) -join ",") -eq "TSK-001,TSK-002,TSK-003") "Critical path task-code order was incorrect"

SendApi Post "/projects/$($project2.id)/members" @{ userId=$engineer.id; roleOnProject="engineer"; assignmentTitle="Second Project Engineer"; projectDiscipline="civil" } $admin | Out-Null
$engProject1 = @(Collection (GetApi "/projects/$($project1.id)/members" $admin)) | Where-Object { $_.userId -eq $engineer.id -and $_.isActive }
$engProject2 = @(Collection (GetApi "/projects/$($project2.id)/members" $admin)) | Where-Object { $_.userId -eq $engineer.id -and $_.isActive }
Assert ($engProject1 -and $engProject2) "Multiple-project membership did not persist"

SendApi Post "/projects/$($project1.id)/members/$($consultant.id)/transfer" @{ targetProjectId=$project2.id } $admin | Out-Null
$sourceConsultant = @(Collection (GetApi "/projects/$($project1.id)/members" $admin)) | Where-Object userId -eq $consultant.id | Select-Object -First 1
$targetConsultant = @(Collection (GetApi "/projects/$($project2.id)/members" $admin)) | Where-Object { $_.userId -eq $consultant.id -and $_.isActive } | Select-Object -First 1
Assert ((-not $sourceConsultant.isActive) -and $targetConsultant) "Administrator transfer membership state failed"

Invoke-RestMethod -Method Delete -Uri "$BaseUrl/projects/$($project1.id)/members/$($engineer.id)" -Headers (Headers $admin) | Out-Null
$sourceEngineer = @(Collection (GetApi "/projects/$($project1.id)/members" $admin)) | Where-Object userId -eq $engineer.id | Select-Object -First 1
$preservedEngineer = @(Collection (GetApi "/users" $admin)) | Where-Object id -eq $engineer.id | Select-Object -First 1
$preservedOtherMembership = @(Collection (GetApi "/projects/$($project2.id)/members" $admin)) | Where-Object { $_.userId -eq $engineer.id -and $_.isActive } | Select-Object -First 1
Assert ((-not $sourceEngineer.isActive) -and $preservedEngineer -and $preservedOtherMembership) "Membership removal affected the global account or another project"
$task1AfterRemoval = GetApi "/tasks/$($task1.id)" $pm
Assert (@($task1AfterRemoval.assigneeIds).Count -eq 0 -and @($task1AfterRemoval.assignees).Count -eq 0) "Admin removal did not safely return active tasks to the unassigned queue"

$audits = @(Collection (GetApi "/audit-logs?limit=500" $admin))
foreach ($action in @("project_member_assigned","site_engineer_assigned","project_member_transferred_out","project_member_transferred_in","project_member_removed")) {
  Assert (@($audits | Where-Object action -eq $action).Count -gt 0) "Missing audit action: $action"
}
$consultantToken = Login "consultant@constro.io"
$engineerNotifications = @((GetApi "/notifications?limit=100" $engineerToken).items)
$consultantNotifications = @((GetApi "/notifications?limit=100" $consultantToken).items)
Assert (@($engineerNotifications | Where-Object title -eq "Project Assignment Removed").Count -gt 0) "Engineer removal notification missing"
Assert (@($consultantNotifications | Where-Object title -eq "Project Assignment Transferred").Count -gt 0) "Consultant transfer notification missing"

[pscustomobject]@{
  Run = $run
  TaskCodes = @($task1.taskCode,$task2.taskCode,$task3.taskCode,$next.taskCode)
  IndependentProjectCode = $otherTask.taskCode
  CriticalPathCodes = @($critical.criticalTasks | Select-Object -ExpandProperty taskCode)
  CriticalPathDuration = $critical.projectDurationDays
  AssigneeRoles = @($eligible | Select-Object -ExpandProperty roleOnProject)
  MultipleTaskAssignees = $true
  AdminMultiProject = [bool]($engProject1 -and $engProject2)
  AdminTransfer = [bool]$targetConsultant
  GlobalAccountsPreserved = [bool]($preservedEngineer -and $targetConsultant.user)
  AuditActionsVerified = $true
  NotificationsVerified = $true
} | ConvertTo-Json -Depth 6
