import {AbsoluteFill,Sequence} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from '../visuals';
export const Assets=()=> <AbsoluteFill><Background/><Brand section="FROM ISSUE TO REQUEST"/>
<Heading eyebrow="Step 1 · Select the affected asset" title="Eight familiar starting points."/><StepPills active={0}/>
<Sequence durationInFrames={170}><Screen src="02_asset_picker.png" crop={{x:340,y:283,w:1220,h:570}} contain zoom={1}/></Sequence>
<Sequence from={158}><Screen src="02b_asset_buttons.png" crop={{x:330,y:420,w:1230,h:430}} zoom={1}>
<Callout text="Eight shortcuts — or describe another issue." x={720} y={10} w={960} delay={30} target={{x:14,y:448,w:300,h:63}}/>
</Screen></Sequence></AbsoluteFill>;
