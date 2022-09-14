FROM registry.ci.openshift.org/ocp/4.12:cli as cli

FROM registry.ci.openshift.org/origin/centos:stream8
LABEL maintainer="brawilli@redhat.com"

COPY --from=cli /usr/bin/oc /usr/bin/

ADD . /openshift-client-python

RUN yum install -y python2 python3 git && python2 -m pip install --upgrade pip && python2 -m pip install -r /openshift-client-python/requirements.txt && python3 -m pip install --upgrade pip && python3 -m pip install -r /openshift-client-python/requirements.txt 

ENV PYTHONPATH=/openshift-client-python/packages:$PYTHONPATH
ENV PYTHONUNBUFFERED=1

ENTRYPOINT /usr/bin/bash
