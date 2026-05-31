from setuptools import setup

package_name = 'voice_capture'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='legend',
    maintainer_email='ahlijin@163.com',
    description='Audio capture node for Orbbec Astra Pro microphone',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'voice_capture_node = voice_capture.voice_capture_node:main',
        ],
    },
)