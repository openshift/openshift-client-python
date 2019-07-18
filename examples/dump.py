#!/usr/bin/env python

from __future__ import unicode_literals
import openshift as oc

if __name__ == '__main__':
    with oc.client_host():
        oc.dumpinfo_system('dumps/', num_combined_journal_entries=50, num_critical_journal_entries=50, logs_since='1h', logs_tail=500)
