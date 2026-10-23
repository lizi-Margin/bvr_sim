Rockwell B-1B Lancer "The Bone"


This aircraft model represents a hack of the B-1B variable wingsweep bomber. The available sweep angles are 15 (takeoff) 25 (slow flight) 45 (high altitude flight) 55/67 (low and high altitude fast flight). The wingsweep is simulated by adding lift/drag to the inner wing part. The outer wing part always stays at 67 degrees and represents the most accurate hack ;-). Afterburner is used for takeoff and for rapid climb/acceleration maneuvers.
The bone is limited to 3g at wartime (currently warning light flashes at 4g), so turning radius is huge at high speeds.

Plane starts with:
- engines off
- parking brake off
- with 190000lb of fuel (full), some space is required to be able to trim the aircraft
- you can immediately change fuel/weapon status in the B-1B menu, but only on the ground.

XXXX INSTRUCTIONS XXXX


Get on/offboard:

- Switch to WSO view (aft cabin)
- Look for Hatch handle on the floor and pull it to OPEN if you want to get out
  or to CLOSE if you just boarded

Start engine:

- Switch main battery switch to ON (overhead middle)
- Switch left(L) and right(R) APU on by switching MODE to ON/START (overhead left top)
- 1st Method:
-   Switch L DRIVE/R DRIVE to 2/4 ADS COUPLE
-   Switch engines 1,2,3,4 to ON (middle console, aft)
- 2nd Method:
-   Switches to L/R BLEED AIR from OFF
-   Switch engines ENG 1,2,3,4 to ON (middle console, aft)
- Note: In case only one APU is running, switch to CRSVR AIR to allow engines 
        in other nacelle to be started (left APU starts engine 1,2; right APU ->3,4
- After engine start switch everything back to off, and switch off APUs now or
  after takeoff climb if you expect to use full power (short field takeoff)
- Engine shutdown sequence: 4,3,2,1 switches to OFF (middle console, aft)

Takeoff:

- swing wing to most forward position (15) --> button F/f (present at start)
- apply 1/2 flaps
- apply full throttle
- apply afterburners
- rotate at 160 - takeoff at 170/180 with full fuel weight
- climb out with full afterburner, normally at 8 degrees
- at 100ft above AGL retract gear, at 270 knots retract flaps
- at 330 Knots operate wingsweep to 25 degrees
- climb out until 360 knots with full afterburner

Flight:

- dependent on your altitude and speed choose 15/25/45/55/67 degrees wingweep (f/F)
- max speed at sea level is mach 1.2, at altitude mach 1.4, short periods 
  at mach 1.5 for fast escape are possible, but you put the wings on danger to twist on maneuvering
- typical performance speed is around mach 0.8 - 0.95 @sea level and mach 0.9 - 1.3 at altitude.

- 15 degrees ws: used for takeoff/landing <320 knots @ sealevel
- 25 degrees ws: used for slow flight/refuelling < 360 knots @sealevel
- 45 degrees ws: used for cruise at high altitude (mach 0.6 - 0.75)
- 55 degrees ws: used for high/low alt flight (above mach 0.7)
- 67 degrees ws: used for high/low alt flight (above mach 0.8)


Landing:

- use 1/2 spoilers to decelerate
- ws 15 degrees
- use 1/2 flaps, approach speed is about 210-230 knots
- on short final use full flaps, speed 170-180 knots
- touchdown speed is ~180 knots with full fuel load, or 145 nearly empty
- on touchdown apply full spoilers, decelerate to 130 knots then
- apply brakes to full stop and use elevator as speedbrake when below 90 knots (pull stick)

Flight performance (especially TO/Landing) heavily depends on aircraft weight!

In Flight Refueling:

- Switch in AERIAL REFUEL panel SLIPWAY switch to ON (overhead middle)
- Pull PULL REFUEL to open refuel door and enable the plane for aerial refuel
- When desired amount of fuel is onboard (max 190000lb! watch TOTAL FUEL cockpit display
  on panel (middle right)
- Pull PULL REFUEL again to shut valves and close door
- Switch SLIPWAY switch to OFF

Fire extinguish system:(not in use atm)

- Set desired APU/engine on fire in top B-1B menu
- Press warning button (panel middle), that automatically switches off the engine/APU 
  and operates fire discharge bottle
- When light extinguishes monitor if engine is down
- Select emergency airport
- Engine/APU is damaged and should not be restarted

Afterburner:

Automatically engaged at full throttle, but with the switches directly behind the throttle levers (ALTER THROT)
 the afterburners for each engine can be deactivated (DECR) or activated (INCR). 
Important when using the autopilot: Switch the afterburners for eng 1 and 4 off, depending on flight also for
eng 3 or/and eng 4. This prevents oscillations of the throttle levers.

XXXX TERRAIN AVOIDANCE / FOLLOWING SYSTEMS XXXX

Terrain Avoidance System (TAS)

Master switch activates terrain avoidance system (tas) (ON/OFF), range knob(RNG) setting for short distance terrain recognition setting (2.5)nm used for slow flying or a hard ride or switch to the medium setting (5)nm thats is used when flying faster (above 400kts @sl) and/or u want a more comfortably ride.
The CLR PLN settings are important as it clears terrain below the aircraft. The settings are 0, 100ft, 300ft, 500ft and 1000ft.
When the terrain avoid system gets active, it adds the desired clearance distance (CLR PLN) to your altitude and guides u over an obstacle. Afterwards it stays in horizontal flying mode, if you want e.g.:altitude hold mode you have to enable it manually again.

Terrain Following System (TFS)

There is a basic terrain following system (TFS) present. You have to enable the master switch ON/OFF, then the PRTY switch to TERRAIN FOLLOW. The PRTY switch toggles the build in tfs from flightgear named MAP(doesn't work very well with with tas) or enables the new tfs, native to the bone, by switching to TERRAIN FOLLOW especially when using the tas. The advantage of the new TFS system is its ability to look forward to scan the terrain in front of the plane.

The native tfs and the build in flightgear tfs(MAP) use the clearance settings from SET CLR.
The clearance settings start from 0ft and increase in 200ft increments up to 2000ft. A=0ft, B=200ft, C=400ft,..., F=1000ft,..., K=2000ft.


XXXX FCGMS Center of Gravity System XXXX

This system sets the Center of Gravity (CG) in % of MAC, and lets you manipulate it in a destinct range. Enable the system by switching on SET on the FCGMS panel and choose your desired CG position. The display to the right shows your current CG position. This is done by using shifting fuel between 2 tanks, so the system works only within a certain margin.

XXXX CDU-900 SYSTEM XXXXX

The CDU is an integrated flight computer currently used to visualize/manipulate NAV and COM properties.
At the moment the topmost  left/right aerrow buttons are used to skip through the submenus, select desired value to change
with the aerrow buttons (right side aerrows) and manipulate with the num block navigation (up/down=coarse,left/right=fine).
You can access the main menus by direct selection on the uppermost row of buttons.


XXXX WEAPON SYSTEM XXXX

This plane is equipped with a bomb guiding system currently working on the intermediate bay. First select weapons
 by going to B-1B/Weapons menu and select LOAD GUIDED(intmd bay loaded with 8 GBU-31 guidable weapons). 
Switch to the OSO seat/view and you should see the GBU31 indicated on SMS display.


Release of guided weapons(only intmd bay currently):

In air prior to release arm your weapons by using the SMS panel. First click on the BAY (should be highlighted when selected),
 then on the station number to arm, then press ARM button(indicated on panel) or SAFE the weapon.
You can rotate the launcher by selecting bay and then press LAUNCHER ROT, the position of the launcher is indicated by an L on the SMS display.


You can use up to 8 guided weapons independently, but I would advise to use 1 or 2 at the beginning.

1.)Arm 1-2 weapons using the SMS panel (about 5min prior to target)
2.)Retrieve target coordinates:

2a.)Type in manually at the OSO view position via the IKB (can be done long before reaching target) or
2b.)Switch to sniper pod view and click with your mouse on target and press t to confirm, next target: press r, then click on target and press t again (should always see confirmation dialog on screen);
3.)Activate target tracking by clicking (in BOMB/NAV panel/ -->STEER --> BOMB button with triangle) the left/upper button  - should be highlighted when active. Typically done at ~25nm to target.
4.)Intmd bay door opening is automated now
5.)When about 15nm away from target, click on the button with the triangle below -->BOMB in BOM/NAV panel to activate the release timer;
6.)Wait for the realease of the weapons, then you can take control of the aircraft and change course if you wish
7.)After releasing the bombs, click on the button with the triangle below BOMB in BOM/NAV panel to de-activate the release timer; and you have to stop the target tracking too if you do not intend to release further bombs; close bay doors manually;

ad 2a.)Using the IKB for manual target coordinats input:
- use left aerrow buttons for quick selection/navigation
- top button (up aerrow) brings you back to main menu
- select STATN1 --> click aerrow button right to SET IKB
- now click on the num buttons of IKB to input coordinates, below you can see at wich pos you currently are
- with the BS and AS you can change the digit to change (none visible means 0)
- first digit (0) sets negative/positive coord -(press 0) or +(press 1) (+not shown)
- then press AS to switch to next digit (1), now press 1(for eg 123.4567) or 0 for (023.4567 => 23.4567 shown)
- now proceed for the whole coordinate, when finished press either SET LON or SET LAT and you should see the coordinates updated
- proceed for the next coordinate -> SET LON or LON again and you should see your target coordinates at STATN1 LAT/LON

The method to retrieve coordinates from the flightgear map/mp server, typing them in and closing on the target is not as stressfull as using the sniper pod, but with she sniper pod you can identify targets much better.

Note: Always use ALT hold to maintain level flight and never use TER AVD and TER FOLLOW when releasing the bombs.


XXXX BLAST, FLARES, STROBE, SPOT XXXX

Based on preexisting osg files some eyecandy for engine blast, smoke, vapour and flares was added.


XXXX FEATURES XXXX

serial: FGFS 08107
name: Bad To The Bone

j/k 	decrease/increase spoilers
f	sweep wing backw
F	sweep wing fwd



XXXX PROGRESS XXXX


FDM:	 	beta - in use / needs tuning		95%complete
3D model:	beta - in use / refinements ..		90%complete
Textures:	alpha - in use / ...			65%complete
Animations:	beta - in use / more to come		95%complete
Autopilot:	beta - in use / needs finetuning	90%complete
3Dcockpit:	beta - in use / needs completion	90%complete

XXXX CONTRIBUTING XXXX

The B-1B is part of the official collection of aircrft; the latest
release is always available at http://www.flightgear.org/download.  If
you would like to help improve this aircraft further, please send an
email to flightgear-devel@lists.flightgear.org.

XXXX AUTHORS XXXX

Main 3D model done by Paul Jay Schrenker.

Terms of usage: Released under terms of GPL v2. Falls under the term of "other work" in part 0. Source is the readable text of the .obj & .mtl files themselves.

This model was created via use of Wings3D. Wings3D is an open source 3D modeler and may be found at www.wings3d.com

FDM/Instruments/Animations/3D modelling by Markus Zojer

Many thanks to XIII,jano,mfranz,AndersG for support.

Terms of usage: Released under terms of GPL v2.


Have Fun! Good Luck!

Markus Zojer,  20/03/2010
