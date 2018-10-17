FROM centos:7

RUN yum --enablerepo=extras install -y epel-release && \
    yum install -y git python2 python-pip && \
    pip install paramiko pyyaml prometheus_client && \
    mkdir /openshift-python

COPY packages /openshift-python/packages

ENV PYTHONPATH=/openshift-python/packages
ENV PYTHONUNBUFFERED=1

ENTRYPOINT /bin/sh
