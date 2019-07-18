
node('bastion2') {
    stage('repo-setup') {
        sh "rm -rf git"
        dir('git') {
            dir('openshift-client-python') {
                // This will also create the git/openshift-client-python directory
                checkout scm
                env.PYTHONPATH = "${pwd()}/packages"
                ocp_dir = pwd()
            }
        }
    }


    stage('ansible') {
        dir("${ocp_dir}/ansible") {
            sh "./rebuild_module.sh"
            echo "Verifying that you submitted your PR after running ./rebuild_module.sh"
            sh "git diff --exit-code rebuild_module.digest || (echo 'You need to run ansible/rebuild_module.sh and include changes in this PR' && exit 1)"
        }
    }

    stage('unittests') {
        dir("${ocp_dir}") {
            echo "Running run tests"
            sh "./run_unittests.sh"
        }
    }

}
