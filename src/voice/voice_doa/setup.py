from setuptools import setup

package_name = 'voice_doa'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='legend',
    maintainer_email='ahlijin@163.com',
    description='DOA node for ReSpeaker Mic Array v2.0 (XVF3000) via USB HID',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'voice_doa_node = voice_doa.voice_doa_node:main',
        ],
    },
)
