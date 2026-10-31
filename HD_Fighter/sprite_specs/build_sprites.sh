cd /home/claude/pronane/c_games/sprite_forge
export SFORGE_HD=1 SFORGE_DETAIL=1.7
M="$(cat /tmp/hdf/moves.txt)"
for c in kairo lyra naomi brutus void zap; do
 python3 forge.py build --spec /tmp/hdf/specs/$c.txt --moves "$M" --yaw 90 --frame 192x256 --figure-h 158 --ground-y 244 --pivot-x 92 --quality final --no-glb --no-fbx --no-cache --out /tmp/hdf/full2 > /tmp/hdf/full_$c.log 2>&1 &
done
wait; echo ALLDONE > /tmp/hdf/alldone
