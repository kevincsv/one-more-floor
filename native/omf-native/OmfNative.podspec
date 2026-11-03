Pod::Spec.new do |s|
  s.name = 'OmfNative'
  s.version = '0.1.0'
  s.summary = 'GameCenter + CloudSave plugins for One More Floor Escape'
  s.license = 'Proprietary'
  s.homepage = 'https://github.com/kevincsv/one-more-floor'
  s.author = 'One More Floor'
  s.source = { :git => 'https://github.com/kevincsv/one-more-floor.git', :tag => s.version.to_s }
  s.source_files = 'ios/Sources/**/*.swift'
  s.ios.deployment_target = '15.0'
  s.dependency 'Capacitor'
  s.frameworks = 'GameKit'
  s.swift_version = '5.9'
end
