const $ = id => document.getElementById(id);
let token = "", user, classes = [], revision = 0, pendingStudents = [];
const localDate = new Date();
$("day").value = [localDate.getFullYear(), String(localDate.getMonth()+1).padStart(2,"0"), String(localDate.getDate()).padStart(2,"0")].join("-");
$("today").textContent = localDate.toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"});
async function api(path, options = {}) {
  const response = await fetch(path,{...options,headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Please check your input.");
  return data;
}
function message(text) { $("message").textContent = text; }
async function load() {
  const current = ++revision;
  const id = $("class").value, day = $("day").value, session = $("session").value;
  if (!id || !day) return;
  try {
    const [students, records] = await Promise.all([api("/classes/"+id+"/students"), api("/classes/"+id+"/attendance?"+new URLSearchParams({day,session}))]);
    if (current !== revision) return;
    pendingStudents = students.filter(student => !records.some(record => record.student_id === student.id));
    const canWrite = user.role === "teacher" && classes.find(c => String(c.id) === id).teacher_id === user.id;
    $("bulk").disabled = !canWrite || pendingStudents.length === 0;
    $("export").disabled = !canWrite;
    $("permission").textContent = canWrite ? "You are assigned to this class." : "You have read-only access to this class.";
    $("total").textContent = students.length;
    $("present").textContent = records.filter(r => r.present).length;
    $("pending").textContent = students.length - records.length;
    $("students").replaceChildren();
    for (const student of students) {
      const row = document.createElement("tr"), record = records.find(r => r.student_id === student.id);
      for (const text of [student.name, "ST-"+String(student.id).padStart(3,"0")]) {
        const cell = row.insertCell(); cell.textContent = text;
      }
      const status = document.createElement("span");
      status.className = "badge " + (record ? record.present ? "present" : "absent" : "");
      status.textContent = record ? record.present ? "Present" : "Absent" : "Pending";
      row.insertCell().append(status);
      const actions = row.insertCell();
      for (const present of [true,false]) {
        const button = document.createElement("button");
        button.textContent = present ? "Present" : "Absent";
        button.className = present ? "" : "secondary";
        button.disabled = !canWrite || !!record;
        button.onclick = async () => {
          actions.querySelectorAll("button").forEach(b => b.disabled = true);
          try {
            await api("/classes/"+id+"/attendance",{method:"POST",body:JSON.stringify({student_id:student.id,day,session,present})});
            message("Attendance saved for "+student.name+".");
          } catch(error) { message(error.message); }
          await load(); await loadOperations();
        };
        actions.append(button);
      }
      $("students").append(row);
    }
  } catch(error) { message(error.message); }
}
$("login").onsubmit = async event => {
  event.preventDefault(); token = $("token").value.trim(); revision++;
  $("workspace").hidden = true; $("identity").textContent = "Connecting…";
  try {
    user = await api("/me"); classes = await api("/classes");
    $("class").replaceChildren(...classes.map(c => { const option = document.createElement("option"); option.value=c.id; option.textContent=c.name; return option; }));
    $("identity").textContent = user.role+" · Account "+user.id;
    $("workspace").hidden = false; message(""); await load(); await loadOperations();
  } catch(error) { $("identity").textContent="Disconnected"; message(error.message); }
};
for (const id of ["class","day","session"]) $(id).onchange = load;
$("refresh").onclick = load;
async function health() {
  try { await api("/ready"); $("health").textContent="● Service healthy"; }
  catch { $("health").textContent="● Service unavailable"; }
}
health(); setInterval(health,15000);

async function loadOperations() {
  $("operations").hidden = user.role !== "teacher";
  $("audit-panel").hidden = user.role !== "teacher";
  if (user.role !== "teacher") return;
  try {
    const [ops, events] = await Promise.all([api("/operations"), api("/audit")]);
    $("ops-grid").replaceChildren();
    for (const [label,value] of [
      ["Environment",ops.environment],["Release",ops.version],
      ["Database",ops.database],["Uptime",Math.floor(ops.uptime_seconds/60)+" min"],
      ["Attendance records",ops.attendance_records],["Audit events",ops.audit_events]
    ]) {
      const card = document.createElement("div"), title = document.createElement("span"), data = document.createElement("strong");
      title.textContent=label; data.textContent=value; card.append(title,data); $("ops-grid").append(card);
    }
    $("audit-rows").replaceChildren();
    for (const event of events) {
      const row = document.createElement("tr");
      for (const value of [event.recorded_at,event.name,"Attendance recorded","Teacher "+event.actor_id]) row.insertCell().textContent=value;
      $("audit-rows").append(row);
    }
    if (!events.length) {
      const row=document.createElement("tr"), cell=row.insertCell();
      cell.colSpan=4; cell.textContent="Record attendance to see activity here."; $("audit-rows").append(row);
    }
  } catch(error) { message(error.message); }
}
$("bulk").onclick = async () => {
  $("bulk").disabled=true;
  try {
    await api("/classes/"+$("class").value+"/attendance/batch",{
      method:"POST",body:JSON.stringify({day:$("day").value,session:$("session").value,
      entries:pendingStudents.map(student=>({student_id:student.id,present:true}))})
    });
    message("Pending students marked present.");
  } catch(error) { message(error.message); }
  await load(); await loadOperations();
};
$("export").onclick = async () => {
  try {
    const query=new URLSearchParams({day:$("day").value,session:$("session").value});
    const response=await fetch("/classes/"+$("class").value+"/attendance.csv?"+query,{headers:{Authorization:"Bearer "+token}});
    if (!response.ok) throw new Error("Export failed. Check your account and connection.");
    const url=URL.createObjectURL(await response.blob()), link=document.createElement("a");
    link.href=url; link.download="attendance-"+$("day").value+".csv"; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  } catch(error) { message(error.message); }
};
$("refresh").onclick = async () => { await load(); await loadOperations(); };
setInterval(()=>{ if (user && !$("workspace").hidden) loadOperations(); },30000);
