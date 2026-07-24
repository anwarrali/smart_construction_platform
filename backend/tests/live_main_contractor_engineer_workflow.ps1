param([string]$BaseUrl = "http://localhost:8000/api/v1")

$ErrorActionPreference = "Stop"

function Login([string]$email, [string]$password = "password123") {
  $body = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"
  (Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body).access_token
}
function Headers([string]$token) { @{ Authorization = "Bearer $token" } }
function Api([string]$method, [string]$path, $body, [string]$token) {
  $args = @{ Method=$method; Uri="$BaseUrl$path"; Headers=(Headers $token) }
  if ($null -ne $body) { $args.ContentType="application/json"; $args.Body=($body | ConvertTo-Json -Depth 12) }
  Invoke-RestMethod @args
}
function ExpectStatus([int]$status, [string]$method, [string]$path, $body, [string]$token) {
  try { Api $method $path $body $token | Out-Null; throw "Expected HTTP $status for $method $path" }
  catch {
    $actual = [int]$_.Exception.Response.StatusCode
    if ($actual -ne $status) { throw "Expected HTTP $status for $method $path, received $actual. $($_.Exception.Message)" }
  }
}
function Assert($condition, [string]$message) { if (-not $condition) { throw "ASSERTION FAILED: $message" } }
function Items($value) { if ($value -is [array]) { @($value) } elseif ($null -eq $value) { @() } else { @($value) } }

$run = [guid]::NewGuid().ToString("N").Substring(0, 8)
$admin = Login "admin@constro.io"
$pm = Login "pm@constro.io"
$engineer = Login "civil@constro.io"
$users = Items (Api Get "/users" $null $admin)
$civil = $users | Where-Object email -eq "civil@constro.io" | Select-Object -First 1
$otherCivil = $users | Where-Object email -eq "contractor@constro.io" | Select-Object -First 1
$mechanical = $users | Where-Object email -eq "mech@constro.io" | Select-Object -First 1
$owner = $users | Where-Object email -eq "owner@constro.io" | Select-Object -First 1
$manager = $users | Where-Object email -eq "pm@constro.io" | Select-Object -First 1
Assert ($civil -and $otherCivil -and $mechanical -and $owner -and $manager) "Required seed users are missing"

$project = $null
$outsideProject = $null
$checks = [ordered]@{}
try {
  $project = Api Post "/projects" @{ name="Engineer E2E $run"; ownerId=$owner.id; projectManagerId=$manager.id; status="active" } $admin
  $outsideProject = Api Post "/projects" @{ name="Engineer Outside $run"; ownerId=$owner.id; projectManagerId=$manager.id; status="active" } $admin
  Api Post "/projects/$($project.id)/members" @{ userId=$civil.id; roleOnProject="engineer"; assignmentTitle="Civil Site Engineer"; projectDiscipline="civil"; isSiteEngineer=$true } $admin | Out-Null
  Api Post "/projects/$($project.id)/members" @{ userId=$otherCivil.id; roleOnProject="engineer"; assignmentTitle="Second Civil Engineer"; projectDiscipline="civil" } $admin | Out-Null
  Api Post "/projects/$($project.id)/members" @{ userId=$mechanical.id; roleOnProject="engineer"; assignmentTitle="Mechanical Engineer"; projectDiscipline="mechanical" } $admin | Out-Null

  $checks.login = $true
  $projects = Api Get "/projects?limit=100" $null $engineer
  Assert ($projects.data.id -contains $project.id) "Assigned project is missing"
  Assert ($projects.data.id -notcontains $outsideProject.id) "Unassigned project leaked"
  Assert (($projects.data | Where-Object id -eq $project.id).budgetTotal -eq $null) "Engineer received project financial data"
  $checks.project_scope = $true
  ExpectStatus 403 Get "/projects/$($outsideProject.id)" $null $engineer
  ExpectStatus 403 Get "/dashboard/engineer/projects/$($outsideProject.id)" $null $engineer
  $checks.url_project_idor_blocked = $true

  $task = Api Post "/tasks" @{ projectId=$project.id; name="Civil Foundation Execution $run"; description="Execute and document foundation work"; discipline="civil"; status="todo"; priority="high"; assigneeIds=@($civil.id); plannedStartDate="2026-07-14"; plannedEndDate="2026-07-16" } $pm
  $otherTask = Api Post "/tasks" @{ projectId=$project.id; name="Other Engineer Work $run"; discipline="civil"; status="todo"; priority="medium"; assigneeIds=@($otherCivil.id); plannedStartDate="2026-07-17"; plannedEndDate="2026-07-20" } $pm
  Assert ($task.durationDays -eq 3 -and $otherTask.durationDays -eq 4) "Inclusive task durations are inconsistent"
  $myTasks = Items (Api Get "/tasks/project/$($project.id)" $null $engineer)
  Assert ($myTasks.id -contains $task.id) "Assigned task missing"
  Assert ($myTasks.id -notcontains $otherTask.id) "Another Engineer task leaked"
  $checks.task_scope = $true
  ExpectStatus 403 Get "/tasks/$($otherTask.id)" $null $engineer
  ExpectStatus 403 Put "/tasks/$($otherTask.id)/start" $null $engineer
  $checks.task_idor_blocked = $true

  $task = Api Put "/tasks/$($task.id)/start" $null $engineer
  Assert ($task.status -eq "in_progress" -and $task.actualStartDate) "Task did not start correctly"
  $checks.start_task = $true
  $task = Api Put "/tasks/$($task.id)/progress" @{ progressPercentage=25; note="Excavation and formwork started" } $engineer
  Assert ($task.progressPercentage -eq 25) "Progress was not stored"
  ExpectStatus 422 Put "/tasks/$($task.id)/progress" @{ progressPercentage=101 } $engineer
  ExpectStatus 422 Put "/tasks/$($task.id)/progress" @{ progressPercentage=-1 } $engineer
  ExpectStatus 400 Put "/tasks/$($task.id)/progress" @{ progressPercentage=20 } $engineer
  $checks.progress_validation = $true
  $dashboard = Api Get "/dashboard/engineer/projects/$($project.id)" $null $engineer
  Assert ($dashboard.stats.inProgress -eq 1 -and $dashboard.project.specialization -eq "civil") "Engineer dashboard did not refresh from database data"
  $checks.dashboard_real_data = $true

  $comment = Api Post "/tasks/$($task.id)/comments" @{ content="Concrete inspection checklist prepared." } $engineer
  Assert ($comment.content -match "inspection") "Task comment was not stored"
  Api Post "/tasks/$($task.id)/work-updates" @{ progressPercentage=35; workCompletedToday="Completed reinforcement checks"; remainingWork="Concrete pour"; workersCount=12; equipmentUsed="Concrete vibrator"; materialsUsed="Rebar and spacers" } $engineer | Out-Null
  $checks.comments_and_work_updates = $true

  $pngPath = Join-Path $env:TEMP "engineer-$run.png"
  $badPath = Join-Path $env:TEMP "engineer-$run.exe"
  [IO.File]::WriteAllBytes($pngPath, [byte[]](0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x00))
  [IO.File]::WriteAllBytes($badPath, [byte[]](0x4D,0x5A,0x00,0x00))
  $form = @{ file=Get-Item $pngPath; project_id=$project.id; entity_type="TASK"; entity_id=$task.id }
  $attachment = Invoke-RestMethod -Method Post -Uri "$BaseUrl/attachments/upload" -Headers (Headers $engineer) -Form $form
  Assert ($attachment.entityType -eq "TASK") "Valid task evidence was not uploaded"
  try {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/attachments/upload" -Headers (Headers $engineer) -Form @{ file=Get-Item $badPath; project_id=$project.id; entity_type="TASK"; entity_id=$task.id } | Out-Null
    throw "Invalid file type was accepted"
  } catch { Assert ([int]$_.Exception.Response.StatusCode -eq 415) "Invalid file did not return HTTP 415" }
  $checks.file_validation = $true

  $blocker = Api Post "/tasks/$($task.id)/blockers" @{ category="material_unavailable"; description="Specified concrete admixture is unavailable"; severity="high" } $engineer
  Assert ($blocker.taskId -eq $task.id) "Blocker was not linked to the task"
  $pmIssues = Items (Api Get "/issues?project_id=$($project.id)" $null $pm)
  Assert ($pmIssues.id -contains $blocker.id) "Project Manager cannot see the blocker"
  ExpectStatus 400 Put "/tasks/$($task.id)/resume-after-blocker" $null $engineer
  Api Put "/issues/$($blocker.id)" @{ status="resolved"; resolutionNotes="Approved equivalent admixture delivered" } $pm | Out-Null
  $task = Api Put "/tasks/$($task.id)/resume-after-blocker" $null $engineer
  Assert ($task.status -eq "in_progress") "Task did not resume after blocker resolution"
  $checks.blocker_workflow = $true

  $issue = Api Post "/issues" @{ projectId=$project.id; taskId=$task.id; title="Foundation access conflict $run"; description="Survey team access conflicts with pour route"; category="coordination"; severity="medium" } $engineer
  Assert ($issue.raisedById -eq $civil.id -and $issue.taskId -eq $task.id) "Engineer issue was not stored correctly"
  $checks.issue_creation = $true

  $task = Api Put "/tasks/$($task.id)/progress" @{ progressPercentage=100; note="Execution complete and evidence uploaded" } $engineer
  $task = Api Put "/tasks/$($task.id)/submit-review" $null $engineer
  Assert ($task.status -eq "under_review" -and $task.reviewStatus -eq "pending") "Task did not enter Under Review"
  ExpectStatus 400 Put "/tasks/$($task.id)" @{ status="done" } $engineer
  ExpectStatus 403 Put "/tasks/$($task.id)/approve" @{ comments="Self approved" } $engineer
  try {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/attachments/upload" -Headers (Headers $engineer) -Form $form | Out-Null
    throw "Under Review task evidence was not locked"
  } catch { Assert ([int]$_.Exception.Response.StatusCode -eq 409) "Under Review evidence upload did not return HTTP 409" }
  $checks.review_submission_and_self_approval_block = $true

  $task = Api Put "/tasks/$($task.id)/reject" @{ comments="Honeycombing requires repair"; rejectionReason="Repair concrete surface and upload evidence" } $pm
  Assert ($task.status -eq "rework_required") "Rejected task did not enter Rework Required"
  $reviews = Items (Api Get "/tasks/$($task.id)/reviews" $null $engineer)
  Assert ($reviews.Count -eq 1 -and $reviews[0].rejectionReason -match "Repair") "Rework feedback/history missing"
  $task = Api Put "/tasks/$($task.id)/start-rework" $null $engineer
  $task = Api Put "/tasks/$($task.id)/progress" @{ progressPercentage=80; note="Repair work started" } $engineer
  $task = Api Put "/tasks/$($task.id)/progress" @{ progressPercentage=100; note="Repair complete" } $engineer
  $task = Api Put "/tasks/$($task.id)/submit-review" $null $engineer
  $reviews = Items (Api Get "/tasks/$($task.id)/reviews" $null $engineer)
  Assert ($reviews.Count -eq 2) "Previous review history was overwritten during resubmission"
  $checks.rework_and_resubmission_history = $true

  ExpectStatus 403 Get "/users" $null $engineer
  ExpectStatus 403 Post "/users" @{ email="forbidden.$run@example.com"; fullName="Forbidden"; role="engineer"; engineerAffiliation="main_contractor"; engineerProfile=@{ discipline="civil" } } $engineer
  ExpectStatus 403 Post "/projects" @{ name="Forbidden project"; ownerId=$owner.id; projectManagerId=$manager.id } $engineer
  ExpectStatus 403 Put "/users/$($civil.id)" @{ role="admin" } $engineer
  ExpectStatus 403 Get "/projects/$($project.id)/members" $null $engineer
  ExpectStatus 403 Get "/scheduling/$($project.id)/gantt" $null $engineer
  ExpectStatus 400 Get "/tasks" $null $engineer
  ExpectStatus 400 Get "/issues" $null $engineer
  ExpectStatus 400 Get "/notifications" $null $engineer
  $checks.rbac_and_project_context = $true

  ExpectStatus 400 Post "/tasks" @{ projectId=$project.id; name="Discipline mismatch"; discipline="civil"; status="todo"; priority="medium"; assigneeIds=@($mechanical.id) } $pm
  $checks.discipline_validation = $true

  $draftForm = @{ project_id=$project.id; report_date="2026-07-14"; content="Daily civil execution report"; review_status="draft"; task_id=$task.id; photos=Get-Item $pngPath }
  $draft = Invoke-RestMethod -Method Post -Uri "$BaseUrl/site-reports/submit" -Headers (Headers $engineer) -Form $draftForm
  Assert ($draft.reviewStatus -eq "draft") "Site report draft was not saved"
  $submittedReport = Api Put "/site-reports/$($draft.id)" @{ summaryText="Updated daily civil execution report"; reviewStatus="submitted" } $engineer
  Assert ($submittedReport.reviewStatus -eq "submitted") "Site report draft was not submitted"
  ExpectStatus 409 Put "/site-reports/$($draft.id)" @{ summaryText="Silent overwrite" } $engineer
  $checks.site_report_draft_and_submit = $true

  $notifications = Api Get "/notifications?project_id=$($project.id)&limit=100" $null $engineer
  Assert ($notifications.items.Count -gt 0) "Engineer internal notifications are missing"
  $activities = Items (Api Get "/tasks/$($task.id)/activity" $null $engineer)
  foreach ($action in @("task_started", "progress_updated", "comment_added", "work_update_added", "blocker_reported", "submitted_for_review", "rework_started", "resubmitted_for_review")) {
    Assert ($activities.action -contains $action) "Missing task activity: $action"
  }
  $checks.notifications_and_audit = $true

  [pscustomobject]@{ Status="PASS"; Run=$run; Checks=$checks; TaskId=$task.id; ProjectId=$project.id } | ConvertTo-Json -Depth 8
}
finally {
  Remove-Item -LiteralPath (Join-Path $env:TEMP "engineer-$run.png") -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $env:TEMP "engineer-$run.exe") -ErrorAction SilentlyContinue
  if ($project) { try { Api Delete "/projects/$($project.id)" $null $admin | Out-Null } catch {} }
  if ($outsideProject) { try { Api Delete "/projects/$($outsideProject.id)" $null $admin | Out-Null } catch {} }
}
