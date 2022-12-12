Process
=======

When runnig composes, these scripts help us take care of that. These are what they do:

```
.
├── produce-8.sh        -> Does a full compose, usually ran only for point releases
├── updates-8-devel.sh  -> Does a compose for the devel repo, ran after full or updates compose
├── updates-8-extras.sh -> Does a compose for the extras repo (only ran when there's changes)
├── updates-8-plus.sh   -> Does a compose for the plus repo (only ran when there's changes)
└── updates-8.sh        -> Does an updates compose (no ISOs or images are made)
```
