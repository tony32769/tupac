#!/usr/bin/env sh
#export PYTHONPATH="/home/dywang/dl/caffe/python:/home/dywang/tools:$PATHONPATH"

TOOLS=/home/dywang/dl/caffe/build/tools
LOG=log
MODEL=models
mkdir $LOG
mkdir $MODEL
mkdir images

GLOG_logtostderr=0 \
GLOG_alsologtostderr=1 \
GLOG_stderrthreshold=1 \
GLOG_log_dir=$LOG \
    $TOOLS/caffe train --solver=./solver.prototxt \
    --weights=models.stage01/mnet_iter_1000000.caffemodel \
    --gpu=1

#--weights=../../stage01/models/mnet_iter_550000.caffemodel \
