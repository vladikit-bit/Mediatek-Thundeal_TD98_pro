from mtklab.core.project import Project
from mtklab.experiments.exp02_repeated_structures.exp02_repeated_structures import Exp02RepeatedStructures

project = Project("td98pro")

ctx = project.create_experiment_context("exp02_repeated_structures")

exp = Exp02RepeatedStructures()

result = exp.run(ctx)

print("=" * 60)
print("Status :", result.status)
print("Summary:", result.summary)
print("=" * 60)

project.close()