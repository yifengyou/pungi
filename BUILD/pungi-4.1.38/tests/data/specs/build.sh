#!/bin/bash

# run this script to (re-)generate ../repo and ../repo-krb5-lookaside directories

# Requirements:
#  * createrepo_c
#  * rpmbuild


set -e


DIR=$(dirname $(readlink -f $0))

rm -rf $DIR/../repo
rm -rf $DIR/../repo-krb5-lookaside


for spec in $DIR/*.spec; do
    echo "Building $spec..."
    for target in i686 x86_64 ppc ppc64 s390 s390x; do
        if [ "$(basename $spec)" == "dummy-foo32.spec" ]; then
            if [ "$target" == "x86_64" -o "$target" == "ppc64" -o "$target" == "s390x" ]; then
                continue
            fi
        fi
        if [ "$(basename $spec)" == "dummy-glibc-2.14-4.spec" ]; then
            if [ "$target" == "i686" -o "$target" == "ppc" -o "$target" == "s390" ]; then
                continue
            fi
        fi
        if [ "$(basename $spec)" == "dummy-AdobeReader_enu.spec" ]; then
            continue
        fi
        if [ "$(basename $spec)" == "dummy-skype.spec" ]; then
            continue
        fi
        echo "Building ${spec/.spec/} for $target"
        rpmbuild --quiet --target=$target -ba --nodeps --define "_srcrpmdir $DIR/../repo/src" --define "_rpmdir $DIR/../repo" $spec
    done
done


# AdobeReader_enu is nosrc for i486 -> handle this special case separately
spec="$DIR/dummy-AdobeReader_enu.spec"
target="i486"
echo "Building ${spec/.spec/} for $target"
rpmbuild --quiet --target=$target -ba --nodeps --define "_srcrpmdir $DIR/../repo/src" --define "_rpmdir $DIR/../repo" --define "_sourcedir $DIR" $spec


# Skype is for i586 -> handle this special case separately
# build only binaries
spec="$DIR/dummy-skype.spec"
target="i586"
echo "Building ${spec/.spec/} for $target"
rpmbuild --quiet --target=$target -bb --nodeps --define "_srcrpmdir $DIR/../repo/src" --define "_rpmdir $DIR/../repo" --define "_sourcedir $DIR/" $spec


# create main repo
echo "Creating main repository"
createrepo_c --quiet --update --groupfile $DIR/../dummy-comps.xml $DIR/../repo


# create lookaside repo for krb5
echo "Creating lookaside repository"
mkdir -p $DIR/../repo-krb5-lookaside
cp $(find $DIR/../repo/ -type f -name '*krb5*.rpm') $DIR/../repo-krb5-lookaside
createrepo_c --quiet --update $DIR/../repo-krb5-lookaside


echo "DONE: Test data created"
