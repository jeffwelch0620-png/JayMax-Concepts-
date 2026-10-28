// Fictional B1 local tests only. Never imported by production components.
import { handoffNote, handoffState } from "./managerHandoff";
export const b1Owner = { id: "usr_test", role: "owner", locations: ["berts"] };
export const b1Id = n => "00000000-0000-4000-8000-" + String(n).padStart(12, "0");
export const b1Clone = v => JSON.parse(JSON.stringify(v));
export function b1Fixture() {
  const tasks = ["Partial sauce", "Finished short", "Pending only", "Corrected batch", "Voided batch", "Exact decimal", "Above plan", "Different product"].map((name,i) => {
    const snapshot = {name: "TEST ONLY " + name, product_id:b1Id(100+i),planning_version_id:b1Id(200+i),recipe_version_id:b1Id(300+i),
      unit_profile_id:b1Id(400+i),source_unit:i===7?"portion":"lb",base_unit:i===7?"each":"lb",
      planned_base_quantity:i===5?"4.000000000001":"4"};
    return {id:b1Id(10+i),store_id:"berts",version_id:b1Id(1),included:true,...snapshot,task_snapshot:snapshot};
  });
  const completions=[];
  const progress=tasks.map((t,i)=>{
    const changed=[3,4].includes(i), qty=i===2?"0":i===4?"0":i===5?"3.123456789013":i===6?"5":"3";
    const link={execution_id:b1Id(500+i),acknowledged_batch_event_id:b1Id(600+i),effective_batch_event_id:b1Id((changed?700:600)+i),
      batch_root_id:b1Id(800+i),needs_review:changed,effective_base_quantity:qty};
    if(i!==2) completions.push({execution_id:link.execution_id,task_id:t.id,acknowledged_batch_event_id:link.acknowledged_batch_event_id,
      needs_review:changed,effective_batch:{id:link.effective_batch_event_id,root_id:link.batch_root_id,store_id:"berts",product_id:t.product_id,
        product_version_id:b1Id(900+i),base_unit:t.base_unit,kind:i===4?"void":changed?"replacement":"initial",review_snapshot:{usableBaseOutput:qty}}});
    return {task_id:t.id,status:changed?"needs_review":i===1?"complete":i===2?"open":"in_progress",closed:i===1,needs_review:changed,
      planned_base_quantity:t.planned_base_quantity,effective_base_quantity:qty,reviewed_base_quantity:changed?"0":qty,links:i===2?[]:[link]};
  });
  const prep={store_id:"berts",prep_date:"2026-10-26",track:"daily",revision:4,status:"released",draft_version_id:b1Id(1),
    draft:{id:b1Id(1),store_id:"berts",review_snapshot:{prep_date:"2026-10-26",track:"daily"}},
    release:{id:b1Id(2),action:"release",draft_version_id:b1Id(1)},tasks,completions,progress_supported:true,task_progress:progress};
  const member={id:b1Id(1000),store_id:"berts",name:"TEST ONLY Cook A",active:true};
  const assignments=tasks.map((t,i)=>{
    const current=i===2?null:{id:b1Id(1100+i),store_id:"berts",task_id:t.id,staff_member_id:member.id,revision:1,predecessor_id:null};
    return {task_id:t.id,current,history:current?[current]:[],current_member:current?member:null,roster_changed:i===3};
  });
  const assignment={store_id:"berts",day:"2026-10-26",track:"daily",execution:b1Clone(prep),members:[member],assignments};
  const note=handoffState({business_date:"2026-10-26",prep_track:"daily",previous:handoffNote({business_date:"2026-10-24",prep_track:"daily",
    status:"submitted",action:"submit",first_submitted_at:"2026-10-24T20:00:00Z",summary:"TEST ONLY previous submitted summary"}),
    current:handoffNote({business_date:"2026-10-26",prep_track:"daily"})});
  const businessFacts={prep,assignment,note,counts:[],orders:[],reports:[{status:"pending",quantity:"3"},{status:"rejected",quantity:"3"}]};
  return {prep,assignment,note,businessFacts};
}
