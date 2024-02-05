test:
	./run_unittests.sh
.PHONY: test

clean:
	rm -rf dist packages/openshift_client.egg-info packages/openshift_client/__pycache__ build
.PHONY: clean

release: clean
	python -m build
.PHONY: release

publish-testpypi:
	twine upload --repository testpypi dist/*
.PHONY: publish-testpypi

publish-pypi:
	twine upload --repository pypi dist/*
.PHONY: publish-pypi
