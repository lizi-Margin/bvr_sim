XXXXXX B-2 Spirit (YASim) readme XXXXXX
XXXXXX      Spirit Of Flight     XXXXXX
XXXXXX       AD INEXPLORATA      XXXXXX

XXXXXX  Version Nr: 0011 20022007 XXXXXX


This aircraft model represents a hack of wing-only aircraft as the B-2. The limitations are the FDM on the one side because of its unability to accept airplanes with only one wing, and on the other side the lack of performance and structure data of the aircraft which are surprisingly classified. So the aircraft constructed here represents closely a wing-only aircraft matching the available performance data of the B-2 (3 wings, no vertical stabilizer) with some approximated guesswork. Despite this shortcommings the aircraft performs like a wing only aircraft in many ways, compared to notes from the Holten brothers and Jack Northrop which developed many wing-only aircraft and collected performance data without fly-by-wire support. This is a very crucial issue since the B-2 in real life is flown by computers which process the input of the pilots in a desired output, I doubt that someone ever disabled the computers and controlled everything by hand like it was done on the former wing-only projects. However in this hack you have the possibility to match your flight skills or take the autopilot (bug or true heading) which compensates for sideslip.

XXXX INSTRUCTIONS XXXX

For those of u who just want to start with:

Takeoff:	x Release parking brake
		x Apply full throttle
		x Rotate at 160kts (with full fuel load)
		x Correct yaw/sideslip with rudder control (drag)
		x Retract gear at end of runway
		x Ctrl w toggles the autopilot which corrects sideslip/yaw = easier to fly
			enabled by default; 
		x Climb at 3-4 degrees or approx.2000ft/min (for 0-6000ft 3000ft/min)

Note: Takeoff length with full fuel load approx. 6500ft

Flight:		x Apply 0.4 to 0.7 throttle
		x For longer distances relax and use the autopilot ;)
		x For terrain following flights close to the ground apply 1 step spoilers and use 1/3 fuel

Approach:	x Use spoilers to decelerate/ cut throttle
		x Below 230kts extract gears
		x Use a glideslope of -2 to -3 degrees
		x Use full spoilers to decelerate
		x Touchdown at 170 to 140kts

Note: The aircraft tends to stay airborne so you have to force it down a bit, like in the fighter planes: use a shallow approach!

Important note: If you fly manually and loose control over the yaw/sideslip momentum, just keep the pitch up around 2-3 degrees and keep the plane level to the ground and you wont crash! Now try to compensate yaw to get in control again!

XXXX FEATURES XXXX

serial: FG 07 0088
name: Spirit Of Flight

j/k 	decrease/increase spoilers
o 	open/close fuel hatch
O	open/close cockpit access hatch
Ctrl d 	open/close bomb bay doors
Ctrl j	launches 2 AGM-154 missiles (10 sec delay) - experimental
Ctrl w 	enables autopilot which corrects sideslip/rudder input possible
rudder control  drag spoilers
flap control	GLAS used to pitch down 0/5/10/15/20/25
spoilers	0/0.25/0.5/0.75/1
fuel flow is shown in gallons/h
fuel capacity is shown in lb/h
refueling light F00L upper left, when in refueling radius
refueling code not added because fuel flow is frozen

XXXX DATA USED XXXX

length:		69ft/21.03m
span:		172ft/52.43m
height:		17ft/5.18m
wing area:	5000ft2/465.5m2
weight:		160000lb/72575kg
takeoff(typ):	336500lb/152635kg
fuel cap.:	200000lb/90720kg
thrust:		76000lb/338kN	4xGeneral Electric F118-GE-100 turbofan engines
cruise speed:	447kt @37000ft
max speed:	460kt @40000ft
		421kt @sealevel
ini.climb rate:	3000ft/min
ceiling:	50000ft
range:		6000nm/11000km unrefueled
airfoil: 	supercritical adapted, close to NACA 23015/23012 (thats what I found out, not sure)
crew:		2
B-2 in service:	21

Many more data was estimated from photos or performance descriptions, or approx. calculations were taken out.

XXXX PROGRESS >>>>

FDM:	 	beta - in use / needs finetuning	85%complete
3D model:	beta - in use / more accurate		80%complete
Textures:	beta - in use / too bold, too few	70%complete
Animations:	beta - in use / few missing		90%complete
Autopilot:	alpha - in use / needs tuning		70%complete
3Dcockpit:	alpha - in use / needs completion	45%complete


XXXX MODELLING XXXX

The whole modelling was done using Blender3D and The Gimp. The 3d cockpit panel features were taken from the Instruments3D-folder, the 777-200 and the 787 (thanks for the excellent instruments) and slightly modificated to suit. Thanks to the authors of the B-52F, A-10, A-4, 777-200, 787 and Hunter models which I investigated to get used to the code and how to use it.

If you have performance issues, comment out the 3 instruments in the Models/spirit.xml file and use a HUD instead.

The model was constructed with a low polygon count in mind, so not all features appear exactly as in rl, but I investigated hundrets of photos to get the main structures right. The color may not be exact but it comes close .., you will find dozens of photos representing the B-2 in its actual state which is developing over the years.

Have Fun! Good Luck!

Markus Zojer,  28/01/2007