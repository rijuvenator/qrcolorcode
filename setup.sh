if ! conda env list | grep -q qrcode
then
    conda create --yes -n qrcode python=3.12
fi
conda activate qrcode
conda install --yes --file requirements.txt
