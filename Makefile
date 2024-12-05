test:
	./run_unittests.sh
.PHONY: test

clean:
	find . -type f -name '*.py[co]' -delete -o -type d -name __pycache__ -delete
	rm -rf dist packages/openshift_client.egg-info build
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
