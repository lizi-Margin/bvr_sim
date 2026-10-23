# Welcome

This is a model of the [Fiat G.91](https://en.wikipedia.org/wiki/Fiat_G.91) fighter bomber for the open source flight simulator [FlightGear](https://www.flightgear.org/).

# The Project
The project's motto is: `QUALITY WITHOUT COMPROMISE!`

The G91-R1B Project was born some years ago on an idea by Adriano Bassignana and Massimiliano Cuccarano in order to achieve a high fidelity airplane for the FlightGear flight simulator with GPL 2 .
Initially (from August 2016 to November 2017) FDMs were made with GPL 2 license by Adriano Bassignana, while 3D files were made with GPL 2 license by Massimiliano Cuccarano.

The philosophy of the project is to make a plane that can be the most faithful possible reproduction of the original FIAT G91-R1B aircraft.

There is no limit on the size of 3D files, which means that it may not be possible to run with machines that have more limited GPUs. This limitation is integral to the philosophy of the project, which aims to explore the possibility of achieving high-quality aircraft in a FlightGear environment with a GPL 2 license.

Therefore, anyone who wants to contribute to the original design is invited not to get out of this philosophy, so each object which is implemented MUST be of high quality, it must not see edges on kinds of surfaces, curves to a natural distance to the view (from 30 cm) from any object.

We do not use textures to cover surface problems, the texture quality must conform to the design philosophy. For example, for gauges, the textures used are at least 1024x1024, so that at a close-up view of the instrument, you did not notice unattractive pixellations.

It is currently based on the latest version of FGFS (2024.1) with ALS effects. NB: there is no compatibility with Rembrandt since this graphics engine is too little followed at the development level. However, this limitation may be revised in the future. Therefore this model might be a good platform for testing new ALS effects as some enthusiasts are doing for the Shuttle.

# Development Notes
The .ac file size for the project may seem too much, but it is necessary to have the visual resolution we want. We are aware that it is still possible to remodel some objects to get a smaller dimension to the same quality.

For the FDM we try to structure the files strongly, let's not work with folders that have hundreds of files. We want all of the project to be as ordered as possible so that anyone can work without any collateral damage.

Document Folder: Whenever possible, each folder has a subfolder called "Documentation" that contains the objects that were needed for us to develop that single part or feature. This folder is very important and useful, so it needs to be constantly updated. It is sad to see very beautiful projects but they do not report the documentation on which they were based. Of course the inserted material must be compatible with the GPL license GPL 2. Documentation files must be with GPL licensed formats though of course the PDF files (which is an Adobe format) we accept them as a standard of fact. We do not accept Microsoft Office format files, but only files produced by programs that are compatible with GPL.

The textures are all in .png format and are collected in a subfolder named "Pictures" in each project folder for individual objects. This repetition is necessary to specialize the Textures on each single object. There may be some simplification in the future, but FGFS's XML code currently does not allow to handle a general texture repository for the textures. This means that each Gauge, for example, has its own "Pictures" folder with custom colors for that object.

It is important to customize the colors as we want to create a model for which the inserted objects have their own identity, as in reality.

At present, we do not anticipate an aging of objects, so we want to make a sample of the newly delivered FIAT G91-R1B. The aging of individual parts can happen later, during the development of specific versions or, hopefully, artificially through the in-depth use of ALS functionality.
