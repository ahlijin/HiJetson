import os
from glob import glob
from setuptools import setup

package_name = 'hijetson_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=[],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # launch 与 config 必须保持 <share>/hijetson_bringup/{launch,config} 这个相对结构:
        # launch 文件里用 ../config/*.yaml 取参数
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*.launch.py'))),
        (os.path.join('share', package_name, 'config'), glob(os.path.join('config', '*.yaml'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ahlijin',
    maintainer_email='ahlijin@163.com',
    description='HiJetson launch/config bringup package',
    license='Apache-2.0',
    tests_require=['pytest'],
)
