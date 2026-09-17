import {AbsoluteFill} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from '../visuals';
export const Location=()=> <AbsoluteFill><Background/><Brand section="FEWER LOCATION MISTAKES"/>
<Heading eyebrow="Step 2 · Locate the work" title="Choose the station. Resolve the line."/><StepPills active={1}/>
<Screen src="04_station_first_clementi.png" crop={{x:330,y:245,w:1230,h:440}} zoom={1}>
<Callout text="Clementi → East–West Line" x={920} y={20} w={790} delay={45} target={{x:15,y:156,w:650,h:63}}/>
<Callout text="Interchanges require a serving-line choice." x={780} y={476} w={930} delay={160}/>
</Screen></AbsoluteFill>;
