# setup.py
import os
from setuptools import setup, find_packages

# Function to read the requirements.txt file
def parse_requirements(filename="requirements.txt"):
    with open(os.path.join(os.path.dirname(__file__), filename), 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read the contents of your README file for long description
try:
    with open(os.path.join(os.path.dirname(__file__), 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "AI-powered Pull Request reviewer for Drone CI using LiteLLM."

# Get version from package __init__.py
version = {}
try:
    with open(os.path.join(os.path.dirname(__file__), "src", "drone_ai_pr_reviewer", "__init__.py")) as fp:
        exec(fp.read(), version)
except FileNotFoundError:
    version['__version__'] = "0.1.0-dev" # Fallback version

setup(
    name='drone-ai-pr-reviewer',
    version=version['__version__'],
    author='Ompragash Viswanathan',
    author_email='ansible@linux.com',
    description='A Drone CI plugin for AI-powered Pull Request reviews using LiteLLM.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/ompragash/drone-ai-pr-reviewer',
    license='Apache License 2.0',
    package_dir={'': 'src'},
    packages=find_packages(where='src', exclude=['tests*', '*.tests', '*.tests.*']),
    include_package_data=True,  # Important to include files specified in MANIFEST.in
    install_requires=parse_requirements(),
    python_requires='>=3.8', # Specify your minimum Python version
    entry_points={
        'console_scripts': [
            'drone-ai-pr-reviewer = drone_ai_pr_reviewer.main:main_cli',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
    ],
    keywords='drone ci harness ci code review llm litellm ai pull request pr reviewer',
)