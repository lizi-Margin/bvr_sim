MiG-29 9-12 Fulcrum-A Notes
---------------------------

First let me state up front that I am not a pilot, nor do I have any special knowledge of the MiG-29 other than intensively studying everything I could find under Google. I cannot model a real MiG-29, I simply lack the information and expertise. This simulation was created using publicly available information. It contains no proprietary or restricted data, is not endorsed by any manufacturer, and is meant for entertainment purposes only. This model is being distributed under the GNU GENERAL PUBLIC LICENSE Version 2. If you like something, grab it and use it.

I had two goals: One was to take the underdeveloped Flightgear MiG-29 and make something fun to fly. That MiG had no cockpit and no flight surface animations. It was a very good start on a model, but not much fun to fly. It seemed to me that the MiG-29 of all planes should be fun to fly for someone with a little experience, so I started playing around with it. My second goal was to learn to build an FG plane from the ground up.

There are many variants of the MiG-29 and I had to pick one. I chose the original form, the one the MiG design bureau calls the '9-12' and NATO labeled the 'Fulcrum A'. I did so because it is the type from which the others are descended, and because it is the simplest, especially in cockpit details.

This plane is not meant to be hard to fly. In fact, in my readings I discovered that real pilots find it relatively easy to fly and generally well-behaved for a high-performance aircraft. In Flightgear it is not as twitchy as the Su-37, but is enjoyable, fast (for those who like fast), and responsive. It cannot yet do some of the high angle-of-attack flight which the real plane is noted for (or maybe it can for better virtual pilots), but as I refine the Flight Data Model, that should improve. My FDM is intended to be initially conservative.

The model has two noted quirks, one is real and one is based on the current FDM. First, the MiG-29 is notorious for short legs. It was meant as a front line air superiority fighter, and as such carries a modest fuel load. Launch, kill, and come home, like a short-winged falcon. Second, when taking off especially with the burners lit, the nose will want to come up hard. Be prepared with a little down-elevator.

The plane is still being physically modeled, and until I am totally happy with the external details it would be a waste of time to deal with texture mapping and liveries. So for a while you will find texture problems or even whole sections with no texture. When the modeling is finished, I'll texture map the plane to use the MP livery system.

The instruments and controls are marked in English rather than Russian. I feel the plane really should be done with cyrillic markings, but my Russian isn't up to it and I don't yet have enough clear illustrations to draw from. So I'm forced to default to English. If someone has an interest in helping me make a true Russian version, I'd like to pursue that. Also, given that I know so little about the flight characteristics, if someone has information that could help improve the flight model, I would be delighted to work with you.

And now a few detailed notes...


Afterburners
------------

Reheat currently engages at 90% throttle. You'll see two green right-side annunciator lights come on when the afterburners cut in. Watch your fuel closely when the burners are lit. If you want to enjoy a long flight, stay off the afterburners. Reheat will blow through your fuel in a few minutes. 

I don't know when the real MiG's burner's cut in, but it's probably around 70-90% throttle. I went conservative because of the fuel issue, and at some later time I may allow this to be a configurable setting so pilots can make their own choice. Also I believe the real plane has switches that enable the burners, somewhere on the throttle, but I don't know which control does it. At some point I may build in such a switch or have it on a menu somewhere.

Cockpit
-------

The model's cockpit is currently very crude but most instruments are there and are closely positioned to the real thing. There's no texturing or model refining at this point-- my main goal was to get flight instruments up first. I'll be upgrading the cockpit's appearance as time and interest allows.

The original MiG-29 cockpit is somewhat basic by western standards, but there is a wisdom in that. The cockpit is very similar in layout to earlier Russian aircraft, making it easy for experienced pilots to transition to the later plane. A pilot familiar with the MiG-23 would be almost at home in the MiG-29.

Flight Surfaces
---------------

You've got the usual suspects: ailerons, flaps, rudders, elevons, slats, air brake. I don't know how many flap positions there are, so the model has five at 0, 16, 32, 64, 100%. Similarly I lack information on slat positions, though they may be automated in the real aircraft. I've given them 4 positions. Deploy slats to reduce stalling at high angles of attack at the expense of added drag. The airbrake also has 4 positions. Based on accounts of the real aircraft I suspect the elevator does not give enough flight response and the ailerons may give too much, at least in terms of initial roll accelleration, so those are subject to later tweaking.

You may notice that the ailerons appear to be fixed in a slightly up position. This is not an error. The Mig-29 ailerons have a fixed 5 degree up neutral position, something related to better spin characteristics. You can see this if you look closely in some photographs of the plane at rest.

Instruments
-----------

Fuel Display:

The fuel display looks much like the real thing, but does not function like the real thing. I've studied many photos of the real instrument and to my annoyance I still don't understand exactly how the dang thing reports data. So I've compromised by building the instrument close to the real appearance and adopting my own temporary scheme for its function. The buttons select tanks 1-4, where 1 is the forward fuselage tank, 2 is the aft tank, 3 left wing, 4 right wing. The center tape display then reports the remaining fuel in that tank. The right side scale reports total fuel. It gets the job done. If someone knows exactly how the fuel gauge works, I would be happy to model it.

In the real machine, the 'buttons' are not buttons at all, but indicator lamps that light up when a tank goes empty. There are small orange triangular indicators that appear to lead from the indicator lamps to the primary fuel scale, and these might be animated, somehow indicating the tank's remaining fuel, but I've yet to make sense of it. The main scale shows total fuel, I think, and the right-hand scale...well, I'm not sure, possibly external fuel when present. There is also a right-side annunciator light that goes red when the aircraft is down to emergency fuel, however that is defined. Currently I define it conservatively as 1000 pounds. If that light goes on, it's time to think about heading home.

Control Position Indicator:

This does not exist in the real Aircraft. The position is normally occupied by the combined oxygen display, which I may build later. As a keyboard & mouse flyer lacking a centering joystick, I rely on the controls indicator to see at a glance the position of my control surfaces. To remove this instrument, edit /Models/MiG-29_Instruments and comment out the relevant instrument model and the related line in the noshadow animation at the top of the file. In the real Mig, there is an annunciator light that goes green when stabilizers are neutralized. I've only seen the one light labeled-- in some other Russian aircraft there is a light for elevator, rudder and ailerons, so it's possible there are three such lights. I currently don't illuminate that annunciator.

Attitude Indicator:

This is a temporary instrument until I build the real one. It's surplus from my 1049H. Better than nothing.

HSI:

Currently the HSI is MIA. I'll get around to it.

Landing Gear Indicator:

This is pretty close to the real thing with a few oddities. The lines over the wings show the slats deployed to some degree. The first line under the wings indicate flaps are deployed to some degree. The second line indicates flaps are fully deployed. This may not be the real functionality, but is a guess. The little lines above and below the center fuselage indicate the air brake deployed to some degree. The red dot in the center of the fuselage indicates gear brakes set. In the real plane, this dot indicates the landing gear are in transition. In my current model, I render that as red landing gear icons and reserve the fuselage dot for the brakes. This is the way I originally understood it to work initially, and since I find it more intuitive and don't know where the brake is indicated, I've left things as they are for the moment.

Clock:

The real MiG clock has a few more features, but this one is close and is the proper size. The clock in the MiG-29 is prominent and large because MiG-29 pilots lack many of the fancy features western pilots are used to. For example, there is no fuel flow indicator, so pilots rely on the clock and the fuel gauge when afterburners are engaged. When launching a radar-guided missile, pilots must time the missile flight themselves to know how long to keep the aircraft radar painting the target.

Ramps (throttle positions):

The indicator below the fuel display is supposed to show the position of internal air intake 'ramps' which automatically adjust to keep supersonic air from entering the engines, which apparently is a Bad Thing. Since this isn't currently modeled by the FDM, I use the ramp indicators to show throttle position so keyboard flyers like yours-truly don't have to look to the left all the time.

Instrument lighting:

Cockpit instrument lighting works, but there's no knob yet. It should live on a little panel to the right of the pilot, but I haven't started on that section yet. You can adjust the instrument lighting from the options & settings menu, ctrl-I. You'll find a few other goodies there too.


Other Notes
-----------

The flight model needs work. The flight surfaces and other figures were placed according to the measured positions of the actual model, but that resulted in a center of lift that was too far back-- the model was nose-heavy, too much up-elevator was constantly required, engaging the flaps pitched the nose down considerably, etc. I played with every parameter I could think of until finally the model was tetering on its main gear, so I knew I'd reached the limit. In the end, I decided to shift the wing forward in the FDM (not the 3D model) by just under a meter, which resulted in reasonably balanced flight characteristics. My rationale is that the FDM does not model all possible characteristics of a wing and some things just need tweaking.
 
For general flying I prefer to dump about half the fuel in the #1 tank. This shifts the CG back a little bit and gives better handling for the kind of relatively slow aerobatic flying I like to do. I monitor the #2 tank as my primary fuel indicator. I don't know if this is realistic in the MiG-29, but I do know that in the real Su-27 series the forward tanks are often not loaded for the same reason.

As time and interest permits I have a lot more coming, so if you're interested in this model, stay tuned.


Acknowledgements
----------------

Work on this model began from tinkering with Detlef Faber's MiG-29 model which can be found at flightgear.org. My plane has long since evolved in its own direction, but it would not exist without his original work. Currently the fuselage retains a portion of Detlef's work, and the engine exhaust nozzles are still using his original work. A little of the original FDM remains, but most has been re-worked based on new information and model differences. Most modeling, animations, the cockpit, nasal scripts, etc., are mine, so if it doesn't work, blame me.

Alvaro Castañeda Mendoza "Tuxo" and Wolfram Gottfried "Yakko" have provided invaluable help with testing and de-bugging, and this model owes them a considerable debt.

---
Gary R. Neely "Buckaroo"
January 2009
grneely@gmail.com


