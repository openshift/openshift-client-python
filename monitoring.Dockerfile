FROM centos:7

RUN yum --enablerepo=extras install -y epel-release && \
    yum install -y git python2 python-pip && \
    pip install paramiko pyyaml prometheus_client boto3 slackclient && \
    mkdir /openshift-client-python

COPY packages /openshift-client-python/packages

ENV PYTHONPATH=/openshift-client-python/packages
ENV PYTHONUNBUFFERED=1

ENTRYPOINT /bin/sh
