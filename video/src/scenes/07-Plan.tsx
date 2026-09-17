import {AbsoluteFill,Sequence} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from '../visuals';
export const Plan=()=> <AbsoluteFill><Background/><Brand section="CHECK CONSTRAINTS TOGETHER"/>
<Heading eyebrow="Step 4 · Generate a proposal" title="Fit repairs around fixed commitments."/><StepPills active={3}/>
<Sequence durationInFrames={157}><Screen src="06_planning_gantt.png" crop={{x:330,y:180,w:1230,h:430}} zoom={1}>
<Callout text="Check time and qualified crew together" x={910} y={50} w={790} delay={25} target={{x:13,y:236,w:340,h:64}}/>
</Screen></Sequence>
<Sequence from={145}><Screen src="06_planning_gantt.png" crop={{x:330,y:478,w:1230,h:425}} zoom={1}>
<Callout text="New repairs + fixed commitments" x={885} y={55} w={820} delay={40}/>
</Screen></Sequence></AbsoluteFill>;
