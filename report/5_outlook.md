```{warning}
This is still a draft! Please refer to the PDF version.
```

# 5. Key Takeaways

With this report, we first of all wanted to raise awareness of the challenges that research with living and programmable corpora entails if it claims to be reproducible research. Based on an exemplary corpus archaeology of GerDraCor, we have also illustrated the developments that a living corpus can undergo and that these developments can involve not only the number of corpus elements, but also the structure and metadata of the text files. 

As we have shown, the problem of reproducing research on living corpora, i.e. dynamic epistemic objects, can be understood as a versioning problem. Accordingly, in this report we have introduced versioning techniques for living and programmable corpora and illustrated their use with examples taken from the DraCor platform.

To summarize, our recommendations on versioning are as follows: 
* When working with living corpora, a version control system should always be used; when citing such corpora, the versions should be explicitly and comprehensively indicated. We recommend working with Git and citing Git commits accordingly (see chapter 3).
* When working with programmable corpora, in which data and code are linked and developed in dependence with each other, the entire infrastructure must be versioned. To this end, we recommend using container technology to conserve  the state of data and code at the time when conducting the research. We recommend Docker for containerization (see chapter 4).

Beyond this, it is crucial for reproducible research that there is an overarching awareness and willingness among all those involved in the research process. We hope that this report will also help to strengthen this awareness.