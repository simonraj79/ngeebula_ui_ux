import {AbsoluteFill, Sequence} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from '../visuals';
export const Review=()=> <AbsoluteFill><Background/><Brand section="CLEAR REQUIREMENTS"/>
<Heading eyebrow="Step 3 · Review the request" title="Make the requirements clear."/><StepPills active={2}/>
<Sequence durationInFrames={175}><Screen src="05b_request_review_details.png" crop={{x:330,y:120,w:1230,h:430}} zoom={1}>
<Callout text="Confirm the repair, location and deadline" x={590} y={480} w={1070} delay={25}/>
</Screen></Sequence>
<Sequence from={163}><Screen src="05c_assessed_requirements.png" crop={{x:330,y:250,w:1230,h:430}} zoom={1} label="ASSESSED DEMO REQUEST · REQUIREMENTS REMAIN REVIEWABLE">
<Callout text="Review assessed priority, duration and crew" x={590} y={515} w={1070} delay={25}/>
</Screen></Sequence></AbsoluteFill>;
