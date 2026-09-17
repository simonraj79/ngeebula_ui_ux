import {AbsoluteFill,Sequence} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from '../visuals';
export const Approval=()=> <AbsoluteFill><Background/><Brand section="ACCOUNTABLE DECISIONS"/>
<Heading eyebrow="Step 5 · Approve and track" title="Keep the maintenance chief in control."/><StepPills active={4}/>
<Sequence durationInFrames={192}><Screen src="07c_approval_same_job.png" crop={{x:330,y:430,w:1230,h:430}} zoom={1}>
<Callout text="Record the decision and its rationale" x={70} y={240} w={810} delay={30} target={{x:930,y:515,w:210,h:64}}/>
</Screen></Sequence>
<Sequence from={180}><Screen src="07d_execution_controls.png" crop={{x:330,y:240,w:1230,h:430}} zoom={1}>
<Callout text="Record progress with a reason" x={900} y={35} w={790} delay={25} target={{x:35,y:440,w:280,h:65}}/>
</Screen></Sequence></AbsoluteFill>;
