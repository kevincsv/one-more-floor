# Añade App.entitlements al target App (usa la gema xcodeproj que trae CocoaPods).
require 'xcodeproj'
proj_path = ARGV[0] || 'ios/App/App.xcodeproj'
proj = Xcodeproj::Project.open(proj_path)
target = proj.targets.find { |t| t.name == 'App' } or abort 'No encuentro el target App'
group = proj.main_group.find_subpath('App', false) || proj.main_group
group.files.find { |f| f.path == 'App.entitlements' } || group.new_reference('App.entitlements')
target.build_configurations.each { |c| c.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'App/App.entitlements' }
proj.save
puts "Entitlements añadidos a #{target.name}"
