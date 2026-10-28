import {assignmentOverview,loadAssignmentOverview} from "./managerAssignmentOverview";
import {b1PrepOverview,overviewContext} from "./managerOverview";
import {b1Fixture,b1Owner,b1Id} from "../testFixtures/managerB1";
const c=overviewContext("berts","2026-10-26","daily",b1Owner);
const project=f=>assignmentOverview(f.assignment,c,b1PrepOverview(f.prep,c));
test("T08 assignments retain IDs and revisions; unassigned and changed roster differ",()=>{const v=project(b1Fixture());expect(v.tasks[0]).toMatchObject({responsibility:"Assigned as recorded",revision:1,memberId:b1Id(1000)});expect(v.tasks[2].responsibility).toBe("Unassigned");expect(v.tasks[3].responsibility).toBe("Needs review");});
test("T08 inactive or missing member is review-required",()=>{const f=b1Fixture();f.assignment.members[0].active=false;expect(project(f).tasks[0].responsibility).toBe("Needs review");f.assignment.assignments[0].current_member=null;expect(project(f).tasks[0].responsibility).toBe("Needs review");});
test.each([
 f=>{f.assignment.execution.revision++;},f=>{f.assignment.execution.status="draft";},f=>{f.assignment.execution.draft_version_id=b1Id(98);},
 f=>{f.assignment.store_id="rudds";},f=>{f.assignment.day="2026-10-25";},f=>{f.assignment.track="bulk";},
 f=>{f.assignment.members[0].store_id="rudds";},f=>{f.assignment.members.push(f.assignment.members[0]);},
 f=>{f.assignment.assignments[0].history[0].store_id="rudds";},f=>{f.assignment.assignments[0].history[0].predecessor_id=b1Id(9);},
 f=>{f.assignment.assignments[0].task_id=b1Id(999);},f=>{f.assignment.assignments[0].current_member={...f.assignment.members[0],name:"Foreign name"};},
 f=>{f.assignment.assignments.push(f.assignment.assignments[0]);}
])("T06 mismatched/duplicate assignment evidence refused %#",change=>{const f=b1Fixture();change(f);expect(()=>project(f)).toThrow();});
test("T12 disabled assignments never read; failed reads use safe status",async()=>{const f=b1Fixture(),api={prepExecutionEnabled:true,staffPrepTasksEnabled:false,staffPrepTaskSetup:jest.fn().mockRejectedValue(new Error("PRIVATE"))},p=b1PrepOverview(f.prep,c);expect((await loadAssignmentOverview(c,p,api)).reason).toBe("disabled");expect(api.staffPrepTaskSetup).not.toHaveBeenCalled();api.staffPrepTasksEnabled=true;const failed=await loadAssignmentOverview(c,p,api);expect(failed.reason).toBe("error");expect(JSON.stringify(failed)).not.toContain("PRIVATE");});
