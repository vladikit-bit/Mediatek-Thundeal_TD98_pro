from mtklab.core.project import Project
from mtklab.experiments.exp01_entropy_landscape.exp01_entropy_landscape import Exp01EntropyLandscape

project = Project("td98pro")

try:
    ctx = project.create_experiment_context("exp01_entropy_landscape")

    exp = Exp01EntropyLandscape()
    result = exp.run(ctx)

    print("=" * 60)
    print("Status :", result.status)
    print("Summary:", result.summary)
    print("=" * 60)

finally:
    project.close()