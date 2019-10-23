from setuptools import setup

setup(
    name='stellar',
    version='0.0.1',
    url='https://github.com/svandecappelle/stellar',
    description='Game',
    author='Steeve Vandecappelle',
    license='MIT',

    # ...,
    setup_requires=["pytest-runner"],
    tests_require=["pytest"],
    # ...,
)
