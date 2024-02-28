```{warning}
This is still a draft! Please refer to the PDF version.
```

# 1. Summary

Digital corpora, which are proving more and more to be the most important epistemic objects of Computational Literary Studies (CLS), are by no means always static objects. On the contrary, it is becoming increasingly clear that the digitisation of our cultural heritage needs to be understood as an ongoing process, which also implies that a number of the epistemic objects of CLS must be conceptualized as genuinely dynamic. We address this specific quality of some epistemic objects of the CLS by speaking of "living corpora". Where corpora — as the *data* of CLS — are also conceptually combined with *code* (e.g. in the form of an API) to form more complex research artifacts, we speak of "programmable corpora", as described in detail in CLS INFRA Deliverable [D7.1 "On Programmable Corpora"](https://doi.org/10.5281/zenodo.7664964).

However, both living and programmable corpora prove to be a considerable problem when discussed with regard to the reproducibility of research. This report considers possible solutions for the stabilization of living and programmable corpora and thus shows ways of making them available for reproducing research in a sustainable and long-term manner. 

By recommending Git commits as a way for versioning living corpora, we rely on a well-established and proven tool for distributed version control, which, as we show using a concrete example, can also be used for living corpora. This also offers the possibility of retrieving additional (technical and performative) metadata about corpora. 
For the more complex programmable corpora, on the other hand, we recommend the containerization of the entire tactical research infrastructure.

In a broader sense, this report is also an exploration of the performative traces left by a living corpus in the technical space of a Git-based version control system. The traces are recovered using a method that we call “algorithmic corpus archaeology” – a method which we recommend to all those who embark on the epistemological adventure of working with living and programmable corpora.